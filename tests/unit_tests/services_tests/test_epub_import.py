import zipfile
from pathlib import Path

import pytest
from PIL import Image

from mealie.services.recipe.pdf_import import epub_document
from mealie.services.recipe.pdf_import.cookbook_document import (
    CookbookReadError,
    EpubCookbook,
    PdfCookbook,
    open_cookbook,
)
from mealie.services.recipe.pdf_import.epub_document import EpubReadError, is_epub, read_epub, save_largest_image
from mealie.services.recipe.pdf_import.pdf_document import PdfPage
from tests.utils.epub_builder import EpubChapterSpec, EpubImageSpec, build_epub
from tests.utils.pdf_builder import PdfPageSpec, build_pdf

PHOTO = EpubImageSpec(name="pancakes.jpg", width=800, height=600, color=(200, 80, 40))
BIG_PHOTO = EpubImageSpec(name="waffles.jpg", width=1200, height=900, color=(40, 80, 200))
ICON = EpubImageSpec(name="icon.jpg", width=40, height=40, color=(0, 0, 0))


def test_each_chapter_and_top_level_heading_starts_a_page(tmp_path: Path):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"),
        [
            EpubChapterSpec("<h1>Breakfast Book</h1>"),
            EpubChapterSpec(
                "<h1>Breakfast</h1><p>Recipes for the morning.</p>"
                "<h2>Pancakes</h2><h3>Ingredients</h3><ul><li>2 eggs</li><li>1 cup flour</li></ul>"
                "<h3>Instructions</h3><ol><li>Mix.</li><li>Cook.</li></ol>"
                "<h2>Waffles</h2><p>2 eggs<br/>1 cup milk</p>"
            ),
        ],
    )

    book = read_epub(epub)

    assert book.pages == [
        PdfPage(number=1, text="Breakfast Book"),
        PdfPage(number=2, text="Breakfast\nRecipes for the morning."),
        # lower headings label the parts of a recipe, so they stay on its page
        PdfPage(number=3, text="Pancakes\nIngredients\n2 eggs\n1 cup flour\nInstructions\nMix.\nCook."),
        PdfPage(number=4, text="Waffles\n2 eggs\n1 cup milk"),
    ]


def test_long_chapters_are_cut_into_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(epub_document, "PAGE_MAX_CHARS", 100)
    paragraphs = [f"Step {i}: " + "stir the pot " * 3 for i in range(10)]
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"),
        [EpubChapterSpec("".join(f"<p>{text}</p>" for text in paragraphs) + f"<p>{'word ' * 60}</p>")],
    )

    pages = read_epub(epub).pages

    assert len(pages) > 3
    assert all(len(page.text) <= 100 for page in pages)
    # nothing is lost in the cutting
    assert " ".join(page.text.replace("\n", " ") for page in pages).split() == (
        " ".join([*paragraphs, "word " * 60]).split()
    )


def test_images_belong_to_the_page_they_lead_into(tmp_path: Path):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"),
        [
            EpubChapterSpec(
                '<h2>Pancakes</h2><p>2 eggs</p><div><img src="../images/waffles.jpg" alt=""/></div>'
                "<h2>Waffles</h2><p>2 eggs</p>"
                '<h2>Omelette</h2><p>3 eggs</p><p><img src="../images/icon.jpg"/></p><p>Fold it.</p>',
                images=[BIG_PHOTO, ICON],
            ),
        ],
    )

    book = read_epub(epub)

    assert [page.text.splitlines()[0] for page in book.pages] == ["Pancakes", "Waffles", "Omelette"]
    # a photo printed before a recipe's title is that recipe's
    assert book.images == {2: ["OEBPS/images/waffles.jpg"], 3: ["OEBPS/images/icon.jpg"]}


def test_the_photo_is_the_largest_image_big_enough_to_be_one(tmp_path: Path):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"),
        [
            EpubChapterSpec(
                '<h2>Pancakes</h2><img src="../images/icon.jpg"/><img src="../images/pancakes.jpg"/><p>2 eggs</p>'
                '<p><img src="../images/waffles.jpg"/></p><p>Serve.</p>',
                images=[ICON, PHOTO, BIG_PHOTO],
            ),
            EpubChapterSpec('<h2>Toast</h2><p>Bread</p><img src="../images/icon.jpg"/><p>Toast it.</p>'),
        ],
    )
    book = read_epub(epub)

    photo = save_largest_image(epub, book, [1], tmp_path.joinpath("photo.jpg"))
    assert photo
    with Image.open(photo) as image:
        assert image.size == (1200, 900)
        red, green, blue = image.convert("RGB").getpixel((600, 450))
        assert blue > red

    # an icon isn't a photo
    assert save_largest_image(epub, book, [2], tmp_path.joinpath("toast.jpg")) is None


@pytest.mark.parametrize("missing", [1, 2])
@pytest.mark.parametrize("missing_manifest", [False, True])
def test_reading_rejects_books_with_present_and_missing_chapters(tmp_path: Path, missing: int, missing_manifest: bool):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"), [EpubChapterSpec("<h2>Pancakes</h2>"), EpubChapterSpec("<h2>Waffles</h2>")]
    )
    # Keep one valid chapter, but remove another file or its manifest entry.
    damaged = tmp_path.joinpath("damaged.epub")
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(damaged, "w") as dest:
        for item in source.infolist():
            data = source.read(item)
            if missing_manifest and item.filename.endswith("content.opf"):
                entry = (
                    f'<item id="chapter-{missing}" href="text/chapter-{missing}.xhtml" '
                    'media-type="application/xhtml+xml"/>'
                )
                data = data.replace(entry.encode(), b"")
            if missing_manifest or not item.filename.endswith(f"chapter-{missing}.xhtml"):
                dest.writestr(item, data)

    with pytest.raises(EpubReadError, match="missing"):
        read_epub(damaged)


def test_epubs_protected_by_drm_are_rejected(tmp_path: Path):
    epub = build_epub(tmp_path.joinpath("cookbook.epub"), [EpubChapterSpec("<h2>Pancakes</h2>")], encrypt_chapters=True)

    with pytest.raises(EpubReadError, match="DRM"):
        read_epub(epub)


def test_epubs_without_text_are_rejected(tmp_path: Path):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"), [EpubChapterSpec('<img src="../images/pancakes.jpg"/>', images=[PHOTO])]
    )

    with pytest.raises(EpubReadError):
        read_epub(epub)


def test_cookbooks_are_read_by_their_contents_not_their_names(tmp_path: Path):
    epub = build_epub(tmp_path.joinpath("cookbook.pdf"), [EpubChapterSpec("<h2>Pancakes</h2>")])
    pdf = build_pdf(tmp_path.joinpath("cookbook.epub"), [PdfPageSpec(lines=["PANCAKES"])])
    zip_file = tmp_path.joinpath("photos.zip")
    with zipfile.ZipFile(zip_file, "w") as archive:
        archive.writestr("photo.txt", "not a book")

    assert is_epub(epub)
    assert not is_epub(pdf)
    assert not is_epub(zip_file)
    assert isinstance(open_cookbook(epub), EpubCookbook)
    assert isinstance(open_cookbook(pdf), PdfCookbook)


@pytest.mark.asyncio
async def test_files_that_arent_cookbooks_cant_be_read(tmp_path: Path):
    text = tmp_path.joinpath("recipes.epub")
    text.write_text("Pancakes: 2 eggs, cook them.")
    zip_file = tmp_path.joinpath("photos.zip")
    with zipfile.ZipFile(zip_file, "w") as archive:
        archive.writestr("photo.txt", "not a book")

    for path in (text, zip_file):
        with pytest.raises(CookbookReadError):
            await open_cookbook(path).check()


def test_chapters_are_limited_by_what_they_unpack_into_not_their_packed_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(epub_document, "MAX_DOCUMENT_BYTES", 100_000)
    # a megabyte of spaces packs into almost nothing
    epub = build_epub(
        tmp_path.joinpath("bomb.epub"),
        [EpubChapterSpec("<h2>Pancakes</h2><p>" + " " * 1_000_000 + "</p>")],
        compress=True,
    )
    assert epub.stat().st_size < 100_000

    with pytest.raises(EpubReadError, match="too large"):
        read_epub(epub)


def test_books_whose_chapters_together_unpack_into_too_much_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    chapter = EpubChapterSpec("<h2>Pancakes</h2><p>" + "2 eggs " * 1000 + "</p>")
    monkeypatch.setattr(epub_document, "MAX_TEXT_BYTES", 12_000)

    assert read_epub(build_epub(tmp_path.joinpath("one.epub"), [chapter], compress=True)).pages
    with pytest.raises(EpubReadError, match="too large"):
        read_epub(build_epub(tmp_path.joinpath("two.epub"), [chapter, chapter], compress=True))


def test_images_too_large_to_be_a_photo_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    epub = build_epub(
        tmp_path.joinpath("cookbook.epub"),
        [EpubChapterSpec('<h2>Pancakes</h2><img src="../images/pancakes.jpg"/><p>2 eggs</p>', images=[PHOTO])],
    )
    book = read_epub(epub)
    assert save_largest_image(epub, book, [1], tmp_path.joinpath("photo.jpg"))

    monkeypatch.setattr(epub_document, "MAX_IMAGE_BYTES", 1000)
    assert save_largest_image(epub, book, [1], tmp_path.joinpath("skipped.jpg")) is None


def test_a_cookbook_sized_book_fits_within_the_limits(tmp_path: Path):
    # a long cookbook kept as one file: thousands of recipes, megabytes of text
    recipe = "<h2>Pancakes</h2><h3>Ingredients</h3><ul>" + "<li>1 cup flour</li>" * 20 + "</ul>" + "<p>Mix.</p>" * 20
    epub = build_epub(tmp_path.joinpath("cookbook.epub"), [EpubChapterSpec(recipe * 3000)], compress=True)
    assert zipfile.ZipFile(epub).getinfo("OEBPS/text/chapter-1.xhtml").file_size > 1_500_000

    assert len(read_epub(epub).pages) == 3000


def test_damaged_chapters_are_reported_as_unreadable(tmp_path: Path):
    epub = build_epub(tmp_path.joinpath("cookbook.epub"), [EpubChapterSpec("<h2>Pancakes</h2>" * 50)], compress=True)
    # flip bytes inside the packed chapter, so it no longer unpacks into what the zip says it does
    with zipfile.ZipFile(epub) as archive:
        info = archive.getinfo("OEBPS/text/chapter-1.xhtml")
    data = bytearray(epub.read_bytes())
    start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    for offset in range(start + 2, start + info.compress_size - 2):
        data[offset] ^= 0xFF
    epub.write_bytes(bytes(data))

    with pytest.raises(EpubReadError):
        read_epub(epub)
