import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass
class EpubImageSpec:
    """An image filled with one color, stored in the EPUB at `images/<name>`"""

    name: str
    width: int
    height: int
    color: tuple[int, int, int] = (200, 80, 40)


@dataclass
class EpubChapterSpec:
    body: str
    """The chapter's HTML, inside its body. Images are at `../images/<name>` from it."""

    images: list[EpubImageSpec] = field(default_factory=list)


def build_epub(
    path: Path, chapters: list[EpubChapterSpec], *, encrypt_chapters: bool = False, compress: bool = False
) -> Path:
    """
    Writes an EPUB 3 with the given chapters, in order, the way ebook tools lay them out. With
    `compress`, the chapters are deflated, as they are in most real books.
    """

    manifest: list[str] = []
    spine: list[str] = []

    with zipfile.ZipFile(path, "w") as epub:
        # the mimetype comes first, uncompressed, so readers can tell what the file is
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )

        for number, chapter in enumerate(chapters, start=1):
            href = f"text/chapter-{number}.xhtml"
            manifest.append(f'<item id="chapter-{number}" href="{href}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="chapter-{number}"/>')
            epub.writestr(
                f"OEBPS/{href}",
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title>'
                f"<style>p {{ margin: 0 }}</style></head><body>{chapter.body}</body></html>",
                compress_type=zipfile.ZIP_DEFLATED if compress else None,
            )

            for image in chapter.images:
                data = io.BytesIO()
                Image.new("RGB", (image.width, image.height), image.color).save(data, "JPEG")
                epub.writestr(f"OEBPS/images/{image.name}", data.getvalue())
                manifest.append(f'<item id="{image.name}" href="images/{image.name}" media-type="image/jpeg"/>')

        epub.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Cookbook</dc:title></metadata>'
            f"<manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>",
        )

        if encrypt_chapters:
            references = "".join(
                "<enc:EncryptedData><enc:CipherData>"
                f'<enc:CipherReference URI="OEBPS/text/chapter-{number}.xhtml"/>'
                "</enc:CipherData></enc:EncryptedData>"
                for number in range(1, len(chapters) + 1)
            )
            epub.writestr(
                "META-INF/encryption.xml",
                '<?xml version="1.0"?>'
                '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                f'xmlns:enc="http://www.w3.org/2001/04/xmlenc#">{references}</encryption>',
            )

    return path
