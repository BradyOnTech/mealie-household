from pathlib import Path

import pytest
from PIL import Image

from mealie.services.recipe.pdf_import import pdf_import_service
from mealie.services.recipe.pdf_import.pdf_document import (
    PdfPage,
    PdfReadError,
    count_pages,
    extract_photo,
    read_pages,
    render_page,
)
from mealie.services.recipe.pdf_import.pdf_import_service import PdfRecipeLocation, _chunk_pages, _settle
from tests.utils.pdf_builder import PAGE_HEIGHT, PAGE_WIDTH, PdfImageSpec, PdfPageSpec, build_pdf

PHOTO = PdfImageSpec(left=300, bottom=300, width=250, height=300, color=(200, 80, 40))
LOGO = PdfImageSpec(left=520, bottom=740, width=40, height=30, color=(0, 0, 255))
BACKGROUND = PdfImageSpec(left=0, bottom=0, width=PAGE_WIDTH, height=PAGE_HEIGHT, color=(250, 245, 230))


def test_read_pages_returns_the_text_on_each_page(tmp_path: Path):
    pdf = build_pdf(
        tmp_path.joinpath("cookbook.pdf"),
        [PdfPageSpec(lines=["PANCAKES", "INGREDIENTS", "2 eggs"]), PdfPageSpec(images=[BACKGROUND])],
    )

    pages = read_pages(pdf)

    assert pages == [PdfPage(number=1, text="PANCAKES\nINGREDIENTS\n2 eggs"), PdfPage(number=2, text="")]
    assert count_pages(pdf) == 2


def test_count_pages_rejects_files_that_arent_pdfs(tmp_path: Path):
    not_a_pdf = tmp_path.joinpath("recipe.pdf")
    not_a_pdf.write_text("just some text")

    with pytest.raises(PdfReadError):
        count_pages(not_a_pdf)


def test_render_page_writes_an_image_of_the_page(tmp_path: Path):
    pdf = build_pdf(tmp_path.joinpath("cookbook.pdf"), [PdfPageSpec(lines=["PANCAKES"], images=[PHOTO])])

    with Image.open(render_page(pdf, 1, tmp_path.joinpath("page.jpg"))) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 1600
        assert image.width / image.height == pytest.approx(PAGE_WIDTH / PAGE_HEIGHT, rel=0.01)


def test_extract_photo_picks_the_largest_photo_on_the_pages(tmp_path: Path):
    smaller = PdfImageSpec(left=72, bottom=72, width=150, height=150, color=(0, 160, 0))
    pdf = build_pdf(
        tmp_path.joinpath("cookbook.pdf"),
        [PdfPageSpec(images=[BACKGROUND, LOGO, smaller]), PdfPageSpec(lines=["PANCAKES"], images=[PHOTO])],
    )

    photo = extract_photo(pdf, [1, 2], tmp_path.joinpath("photo.jpg"))

    assert photo
    with Image.open(photo) as image:
        # the background is too big to be a photo, and the logo too small
        assert image.width / image.height == pytest.approx(PHOTO.width / PHOTO.height, rel=0.02)
        assert image.convert("RGB").getpixel((image.width // 2, image.height // 2)) == pytest.approx(PHOTO.color, abs=8)


def test_extract_photo_crops_to_the_part_on_the_page(tmp_path: Path):
    # hangs off the left edge of the page, so only 200pt of its width shows
    partly_off_page = PdfImageSpec(left=-100, bottom=300, width=300, height=200)
    pdf = build_pdf(tmp_path.joinpath("cookbook.pdf"), [PdfPageSpec(images=[partly_off_page])])

    photo = extract_photo(pdf, [1], tmp_path.joinpath("photo.jpg"))

    assert photo
    with Image.open(photo) as image:
        assert image.width / image.height == pytest.approx(200 / 200, rel=0.02)


def test_extract_photo_returns_none_without_a_photo(tmp_path: Path):
    pdf = build_pdf(tmp_path.joinpath("cookbook.pdf"), [PdfPageSpec(lines=["PANCAKES"], images=[BACKGROUND, LOGO])])

    assert extract_photo(pdf, [1], tmp_path.joinpath("photo.jpg")) is None
    # pages that don't exist are ignored
    assert extract_photo(pdf, [5], tmp_path.joinpath("photo.jpg")) is None


def _pages(*lengths: int) -> list[PdfPage]:
    return [PdfPage(number=i + 1, text="x" * length) for i, length in enumerate(lengths)]


def test_chunk_pages_overlaps_consecutive_chunks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pdf_import_service, "INDEX_MAX_PAGES", 10)
    monkeypatch.setattr(pdf_import_service, "INDEX_OVERLAP_PAGES", 3)

    chunks = _chunk_pages(_pages(*[100] * 25), with_images=True)

    assert [[page.number for page in chunk] for chunk in chunks] == [
        list(range(1, 11)),
        list(range(8, 18)),
        list(range(15, 25)),
        list(range(22, 26)),
    ]


def test_chunk_pages_limits_text_and_images(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pdf_import_service, "INDEX_MAX_CHARS", 1000)
    monkeypatch.setattr(pdf_import_service, "INDEX_MAX_IMAGES", 2)
    monkeypatch.setattr(pdf_import_service, "INDEX_OVERLAP_PAGES", 1)

    by_text = _chunk_pages(_pages(600, 600, 600), with_images=True)
    assert [[page.number for page in chunk] for chunk in by_text] == [[1], [2], [3]]

    # pages without text are sent as images, so they count against the image limit instead
    by_images = _chunk_pages(_pages(0, 0, 0, 0), with_images=True)
    assert [[page.number for page in chunk] for chunk in by_images] == [[1, 2], [2, 3], [3, 4]]

    # unless there's no image provider to send them to
    text_only = _chunk_pages(_pages(0, 0, 0, 0), with_images=False)
    assert [[page.number for page in chunk] for chunk in text_only] == [[1, 2, 3, 4]]


def test_settle_orders_recipes_and_keeps_them_from_overlapping():
    # recipes starting on the same page are numbered in the order they were found
    settled = _settle(
        [
            PdfRecipeLocation("Waffles", 5, 9),
            PdfRecipeLocation("Pancakes", 2, 4),
            PdfRecipeLocation("Syrup", 5, 5),
            PdfRecipeLocation("Omelette", 7, 8),
            PdfRecipeLocation("PANCAKES", 2, 3),
        ]
    )

    assert settled == [
        PdfRecipeLocation("Pancakes", 2, 4),
        PdfRecipeLocation("Waffles", 5, 6),
        PdfRecipeLocation("Syrup", 5, 5, item=1),
        PdfRecipeLocation("Omelette", 7, 8),
    ]
