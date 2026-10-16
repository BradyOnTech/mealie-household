import ctypes
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image

PAGE_WIDTH = 612
PAGE_HEIGHT = 792


@dataclass
class PdfImageSpec:
    """An image filled with one color, placed in PDF points from the bottom-left corner"""

    left: float
    bottom: float
    width: float
    height: float
    color: tuple[int, int, int] = (200, 80, 40)


@dataclass
class PdfPageSpec:
    lines: list[str] = field(default_factory=list)
    """Text lines, laid out from the top of the page down"""

    images: list[PdfImageSpec] = field(default_factory=list)


def _add_text(pdf: pdfium.PdfDocument, page: pdfium.PdfPage, text: str, x: float, y: float) -> None:
    obj = pdfium_c.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", ctypes.c_float(12))
    buffer = ctypes.create_string_buffer((text + "\x00").encode("utf-16-le"))
    pdfium_c.FPDFText_SetText(obj, ctypes.cast(buffer, ctypes.POINTER(pdfium_c.FPDF_WCHAR)))
    pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
    pdfium_c.FPDFPage_InsertObject(page.raw, obj)


def _add_image(pdf: pdfium.PdfDocument, page: pdfium.PdfPage, spec: PdfImageSpec) -> None:
    image = pdfium.PdfImage.new(pdf)
    pixels = Image.new("RGB", (max(int(spec.width), 1), max(int(spec.height), 1)), spec.color)
    image.set_bitmap(pdfium.PdfBitmap.from_pil(pixels))
    image.set_matrix(pdfium.PdfMatrix().scale(spec.width, spec.height).translate(spec.left, spec.bottom))
    page.insert_obj(image)


def build_pdf(path: Path, pages: list[PdfPageSpec]) -> Path:
    """Writes a PDF with a real text layer and images, the way a designed cookbook has them."""

    pdf = pdfium.PdfDocument.new()
    try:
        for spec in pages:
            page = pdf.new_page(PAGE_WIDTH, PAGE_HEIGHT)
            for i, line in enumerate(spec.lines):
                _add_text(pdf, page, line, 72, PAGE_HEIGHT - 72 - i * 18)
            for image in spec.images:
                _add_image(pdf, page, image)
            page.gen_content()
            page.close()

        pdf.save(path)
    finally:
        pdf.close()

    return path
