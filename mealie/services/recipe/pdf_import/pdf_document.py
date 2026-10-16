"""
Reads cookbook PDFs with PDFium: the text on each page, images of whole pages for the AI to look
at, and the photo that goes with a recipe.

PDFium isn't thread-safe, so every call into it should go through `run_pdfium`, which runs one at
a time on a worker thread. Each function opens the document itself rather than sharing one, since
nothing here is hot enough for that to matter and it keeps PDFium state out of the async code.
"""

import asyncio
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

PAGE_IMAGE_MAX_SIDE = 1600
"""Longest side, in pixels, of the page images the AI reads. Enough to read body text comfortably."""

PHOTO_MAX_SIDE = 1600
"""Longest side, in pixels, a recipe photo is rendered at, at most."""

MAX_PHOTO_SCALE = 4.0

MIN_PHOTO_AREA = 0.03
"""Images smaller than this share of the page are icons, logos, or decorations rather than photos."""

MAX_PHOTO_AREA = 0.85
"""Images covering more of the page than this are backgrounds or scans of the whole page."""

RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f￾￿]")

_pdfium_lock = threading.Lock()


class PdfReadError(Exception):
    """The file isn't a PDF that can be read, e.g. it's damaged or protected by a password."""


@dataclass(frozen=True)
class PdfPage:
    number: int
    """1-based, the way people and the AI refer to pages"""

    text: str


async def run_pdfium[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Runs a function that uses PDFium on a worker thread, one at a time."""

    def locked() -> T:
        with _pdfium_lock:
            return fn(*args, **kwargs)

    return await asyncio.to_thread(locked)


def _open(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(path)
    except pdfium.PdfiumError as e:
        raise PdfReadError(str(e)) from e


def _clean_text(text: str) -> str:
    text = RE_CONTROL_CHARS.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))

    lines: list[str] = []
    for line in (line.strip() for line in text.split("\n")):
        # keep paragraph breaks, but never more than one blank line in a row
        if line or (lines and lines[-1]):
            lines.append(line)

    return "\n".join(lines).strip()


def count_pages(path: Path) -> int:
    """Returns the PDF's page count, raising `PdfReadError` if it can't be read or has no pages."""

    pdf = _open(path)
    try:
        page_count = len(pdf)
    finally:
        pdf.close()

    if not page_count:
        raise PdfReadError("The PDF has no pages")
    return page_count


def read_pages(path: Path) -> list[PdfPage]:
    """Returns the text on every page. Pages without a text layer, such as scans, come back empty."""

    pdf = _open(path)
    try:
        pages: list[PdfPage] = []
        for index in range(len(pdf)):
            page = pdf[index]
            text_page = page.get_textpage()
            try:
                pages.append(PdfPage(number=index + 1, text=_clean_text(text_page.get_text_range())))
            finally:
                text_page.close()
                page.close()
        return pages
    finally:
        pdf.close()


def render_page(path: Path, number: int, dest: Path) -> Path:
    """Renders a whole page to a JPEG, for the AI to read."""

    pdf = _open(path)
    try:
        page = pdf[number - 1]
        try:
            width, height = page.get_size()
            scale = min(PAGE_IMAGE_MAX_SIDE / max(width, height), 3.0)
            page.render(scale=scale).to_pil().convert("RGB").save(dest, "JPEG", quality=85)
        finally:
            page.close()
    finally:
        pdf.close()

    return dest


def _render_alone(path: Path, number: int, index: int, scale: float):
    """
    Renders one top-level image on a page with everything else on the page removed, onto a
    transparent background. Drawing it is what applies its clip path, so the opaque pixels are
    exactly the part of the image a reader sees. Reading the clip path instead isn't reliable:
    PDFium can report it in a different space from the image.

    Returns the rendered image, or None if the object isn't an image.
    """

    pdf = _open(path)
    removed: list[pdfium.PdfObject] = []
    try:
        page = pdf[number - 1]
        try:
            objects = [obj for obj in page.get_objects(max_depth=1) if obj.level == 0]
            if index >= len(objects) or objects[index].type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
                return None

            for i, obj in enumerate(objects):
                if i != index:
                    page.remove_obj(obj)
                    removed.append(obj)

            return page.render(scale=scale, fill_color=(0, 0, 0, 0), may_draw_forms=False).to_pil()
        finally:
            # removed objects belong to us now, and must be closed before their page is
            for obj in removed:
                obj.close()
            page.close()
    finally:
        pdf.close()


def _image_indexes(path: Path, numbers: Sequence[int]) -> list[tuple[int, int]]:
    pdf = _open(path)
    try:
        found: list[tuple[int, int]] = []
        for number in numbers:
            if not 1 <= number <= len(pdf):
                continue

            page = pdf[number - 1]
            try:
                objects = [obj for obj in page.get_objects(max_depth=1) if obj.level == 0]
                found.extend((number, i) for i, obj in enumerate(objects) if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE)
            finally:
                page.close()
        return found
    finally:
        pdf.close()


def extract_photo(path: Path, numbers: Sequence[int], dest: Path) -> Path | None:
    """
    Saves the largest photo on the given pages as a JPEG, cropped the way the page shows it.

    Only images placed directly on a page count, not ones nested in form objects. Returns None if
    none of the pages has an image of a plausible size for a photo.
    """

    best: tuple[float, int, int, tuple[int, int, int, int]] | None = None
    for number, index in _image_indexes(path, numbers):
        preview = _render_alone(path, number, index, scale=0.5)
        if preview is None or preview.mode != "RGBA":
            continue

        box = preview.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
        if not box:
            continue

        area = (box[2] - box[0]) * (box[3] - box[1]) / (preview.width * preview.height)
        if MIN_PHOTO_AREA <= area <= MAX_PHOTO_AREA and (best is None or area > best[0]):
            best = (area, number, index, box)

    if best is None:
        return None

    _, number, index, (left, top, right, bottom) = best
    # the preview was rendered at half scale, so its box is in units of 2pt
    scale = min(PHOTO_MAX_SIDE / (max(right - left, bottom - top) * 2), MAX_PHOTO_SCALE)
    image = _render_alone(path, number, index, scale=scale)
    if image is None:
        return None

    box = image.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
    if not box:
        return None

    photo = image.crop(box)
    flattened = photo.convert("RGBA")
    background = flattened.copy()
    background.paste((255, 255, 255, 255), (0, 0, *flattened.size))
    background.alpha_composite(flattened)
    background.convert("RGB").save(dest, "JPEG", quality=90)
    return dest
