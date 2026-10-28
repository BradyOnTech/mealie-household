"""
Reads cookbook EPUBs into pages like a PDF's, so they go through the same import.

An EPUB has no pages, just a book's chapters in reading order as HTML. They're cut into pages
here: every chapter starts a new page, and so does every top-level heading, since cookbooks put
each recipe under one, and a page that's grown long enough is cut at the next line. That keeps
each recipe at the top of its own page, and recipes the same size they'd be in a PDF.

The text of an EPUB is in reading order, unlike a PDF's, so the AI only needs to see an image of a
page that has no text, such as a scanned one. The recipe photo is the largest image on its pages.
"""

import posixpath
import re
import warnings
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urldefrag

from bs4 import BeautifulSoup, CData, NavigableString, PageElement, Tag, XMLParsedAsHTMLWarning
from PIL import Image, UnidentifiedImageError

from .pdf_document import PdfPage, _clean_text

EPUB_MIMETYPE = "application/epub+zip"
HTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}

PAGE_MAX_CHARS = 3000
"""Roughly a printed cookbook page. A longer page is cut at the next line that would take it past this."""

PAGE_BREAK_HEADINGS = {"h1", "h2"}
"""Headings that start a new page. Lower ones label the parts of a recipe, like its ingredients."""

BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "caption", "dd", "div", "dl", "dt", "figcaption", "figure",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "td", "th", "tr", "ul",
}  # fmt: skip

MIN_PHOTO_SIDE = 200
"""Images narrower or shorter than this, in pixels, are icons, dividers, or decorations rather than photos."""

PHOTO_MAX_SIDE = 1600

# An EPUB is a zip, so a small upload can unpack into far more. These are well beyond any real book
# (a whole cookbook's text is a few MB, even when it's all one file, and its photos are each a few MB)
# but stop a file made to unpack into gigabytes.
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
"""The most a chapter or one of the files describing the book can unpack into"""

MAX_TEXT_BYTES = 256 * 1024 * 1024
"""The most all of a book's chapters together can unpack into"""

MAX_IMAGE_BYTES = 64 * 1024 * 1024
"""The most an image file can unpack into. A larger one is skipped, like an image that can't be read."""

# Markers put into the text while reading a chapter, from Unicode's private use area so no book's
# text can contain them: one starts a heading that starts a page, the other pair holds an image's path.
_PAGE_BREAK = ""
_IMAGE_START = ""
_IMAGE_END = ""
RE_IMAGE = re.compile(f"{_IMAGE_START}(.*?){_IMAGE_END}")

RE_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")


class EpubReadError(Exception):
    """The file isn't an EPUB that can be read, e.g. it's damaged or protected by DRM."""


@dataclass
class EpubBook:
    pages: list[PdfPage]
    images: dict[int, list[str]] = field(default_factory=dict)
    """The paths in the EPUB of the images on each page, by page number"""


def is_epub(path: Path) -> bool:
    if not zipfile.is_zipfile(path):
        return False

    try:
        with zipfile.ZipFile(path) as epub:
            names = set(epub.namelist())
            if "mimetype" in names:
                return epub.read("mimetype").decode("ascii", "ignore").strip() == EPUB_MIMETYPE
            return "META-INF/container.xml" in names
    except zipfile.BadZipFile, OSError:
        return False


def _xml(data: bytes) -> BeautifulSoup:
    return BeautifulSoup(data, "xml")


def _read(epub: zipfile.ZipFile, name: str) -> bytes:
    """
    Reads a file in the EPUB, raising `EpubReadError` if it unpacks into more than `MAX_DOCUMENT_BYTES`.
    The size is the one the zip records, which reading it never goes past.
    """

    size = epub.getinfo(name).file_size
    if size > MAX_DOCUMENT_BYTES:
        raise EpubReadError(f"{name} in the EPUB is too large: {size} bytes")

    try:
        return epub.read(name)
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as e:
        # damaged, or packed in a way zipfile can't unpack
        raise EpubReadError(f"{name} in the EPUB can't be read: {e}") from e


def _resolve(base: str, href: str) -> str:
    """The path in the EPUB of `href`, relative to the file at `base`"""

    href = unquote(urldefrag(href).url)
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), href)).lstrip("/")


def _spine(epub: zipfile.ZipFile) -> list[str]:
    """The paths of the book's chapters, in reading order"""

    try:
        container = _xml(_read(epub, "META-INF/container.xml"))
        rootfile = container.find("rootfile")
        opf_path = str(rootfile["full-path"]) if isinstance(rootfile, Tag) else ""
        package = _xml(_read(epub, opf_path))
    except (KeyError, TypeError) as e:
        raise EpubReadError("The EPUB has no package document") from e

    manifest = {
        str(item.get("id")): (_resolve(opf_path, str(item.get("href", ""))), str(item.get("media-type", "")))
        for item in package.find_all("item")
    }

    chapters: list[str] = []
    for itemref in package.find_all("itemref"):
        reference = str(itemref.get("idref"))
        if reference not in manifest:
            raise EpubReadError(f"The EPUB spine references a missing manifest item: {reference}")
        path, media_type = manifest[reference]
        if path and media_type in HTML_MEDIA_TYPES:
            chapters.append(path)
    return chapters


def _encrypted(epub: zipfile.ZipFile) -> set[str]:
    """The paths of the files that are encrypted, usually by DRM. Fonts can be too, which doesn't matter."""

    try:
        encryption = _xml(_read(epub, "META-INF/encryption.xml"))
    except KeyError:
        return set()

    return {
        str(reference.get("URI", "")).lstrip("/")
        for reference in encryption.find_all("CipherReference")
        if reference.get("URI")
    }


def _chapter_lines(data: bytes, chapter: str) -> list[str]:
    """The chapter's text, one block per line, with the markers for page breaks and images."""

    try:
        # EPUB chapters are UTF-8, and decoding them up front skips guessing the encoding
        markup: str | bytes = data.decode("utf-8")
    except UnicodeDecodeError:
        markup = data

    with warnings.catch_warnings():
        # chapters are XHTML, but read as HTML, which is forgiving of the mistakes books often have
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(markup, "lxml")
    body = soup.body or soup

    # Walked rather than edited in place, since inserting into a long chapter's tree takes time that
    # grows with the square of its length. Each item is a node, or a string to add after a block's end.
    parts: list[str] = []
    stack: list[PageElement | str] = [body]
    while stack:
        node = stack.pop()
        if isinstance(node, str) and not isinstance(node, NavigableString):
            parts.append(node)
        elif isinstance(node, NavigableString):
            # the strings `get_text` would include, which leaves out comments and the like
            if type(node) in (NavigableString, CData):
                parts.append(str(node))
        elif isinstance(node, Tag):
            if node.name in ("script", "style"):
                continue
            if node.name in ("img", "image"):
                src = node.get("src") or node.get("xlink:href") or node.get("href")
                if isinstance(src, str) and src:
                    parts.append(f"\n{_IMAGE_START}{_resolve(chapter, src)}{_IMAGE_END}\n")
                    continue
            if node.name == "br":
                parts.append("\n")
                continue

            if node.name in BLOCK_TAGS:
                parts.append("\n" + (_PAGE_BREAK if node.name in PAGE_BREAK_HEADINGS else ""))
                stack.append("\n")
            stack.extend(reversed(node.contents))

    text = RE_HORIZONTAL_SPACE.sub(" ", "".join(parts))
    return [line.strip() for line in text.split("\n") if line.strip()]


def _split_long(line: str) -> list[str]:
    """Cuts a line longer than a page at the spaces nearest the page length."""

    parts: list[str] = []
    while len(line) > PAGE_MAX_CHARS:
        cut = line.rfind(" ", 0, PAGE_MAX_CHARS)
        cut = cut if cut > 0 else PAGE_MAX_CHARS
        parts.append(line[:cut])
        line = line[cut:].strip()
    return [*parts, line] if line else parts


def read_epub(path: Path) -> EpubBook:
    """Reads the book into pages, raising `EpubReadError` if it can't be read or has no text."""

    try:
        epub = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise EpubReadError(str(e)) from e

    with epub:
        chapters = _spine(epub)
        if not chapters:
            raise EpubReadError("The EPUB has no chapters")
        if _encrypted(epub).intersection(chapters):
            raise EpubReadError("The EPUB is protected by DRM")

        pages: list[PdfPage] = []
        images: dict[int, list[str]] = {}
        lines: list[str] = []
        page_images: list[str] = []
        # images since the page's last line of text go with what follows them, like a photo before a recipe's title
        images_after_text: list[str] = []

        def end_page(carry_over: Sequence[str] = ()) -> None:
            kept = page_images[: len(page_images) - len(carry_over)]
            if lines or kept:
                number = len(pages) + 1
                pages.append(PdfPage(number=number, text=_clean_text("\n".join(lines))))
                if kept:
                    images[number] = kept
            lines.clear()
            page_images[:] = carry_over

        text_bytes = 0
        for chapter in chapters:
            try:
                data = _read(epub, chapter)
            except KeyError as e:
                raise EpubReadError(f"The EPUB is missing a spine chapter: {chapter}") from e

            text_bytes += len(data)
            if text_bytes > MAX_TEXT_BYTES:
                raise EpubReadError("The EPUB's chapters are too large")

            chapter_lines = _chapter_lines(data, chapter)

            end_page()
            images_after_text.clear()
            for line in chapter_lines:
                if line.startswith(_PAGE_BREAK) and lines:
                    end_page(carry_over=list(images_after_text))
                line = line.replace(_PAGE_BREAK, "").strip()

                line_images = RE_IMAGE.findall(line)
                page_images.extend(line_images)
                images_after_text.extend(line_images)
                line = RE_IMAGE.sub("", line).strip()
                if not line:
                    continue

                images_after_text.clear()
                for part in _split_long(line):
                    if lines and sum(len(existing) + 1 for existing in lines) + len(part) > PAGE_MAX_CHARS:
                        end_page()
                    lines.append(part)
        end_page()

    if not any(page.text for page in pages):
        raise EpubReadError("The EPUB has no text")

    return EpubBook(pages=pages, images=images)


def _open_image(epub: zipfile.ZipFile, name: str) -> Image.Image | None:
    try:
        if epub.getinfo(name).file_size > MAX_IMAGE_BYTES:
            return None
        with epub.open(name) as f:
            image = Image.open(f)
            image.load()
            return image
    except (
        KeyError,
        OSError,
        EOFError,
        zipfile.BadZipFile,
        zlib.error,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return None


def save_largest_image(path: Path, book: EpubBook, numbers: Sequence[int], dest: Path) -> Path | None:
    """
    Saves the largest image on the given pages as a JPEG. Returns None if none of them is big
    enough to be a photo rather than an icon or a decoration.
    """

    best: tuple[int, Image.Image] | None = None
    with zipfile.ZipFile(path) as epub:
        for number in numbers:
            for name in book.images.get(number, []):
                image = _open_image(epub, name)
                if image is None or min(image.size) < MIN_PHOTO_SIDE:
                    continue

                area = image.width * image.height
                if best is None or area > best[0]:
                    best = (area, image)

    if best is None:
        return None

    image = best[1]
    image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
    flattened = image.convert("RGBA")
    background = Image.new("RGBA", flattened.size, (255, 255, 255, 255))
    background.alpha_composite(flattened)
    background.convert("RGB").save(dest, "JPEG", quality=90)
    return dest
