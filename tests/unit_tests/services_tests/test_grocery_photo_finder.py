"""Finding a product's photo on its store's page, and keeping photos at the sizes they're shown at."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import mealie.services.household_services.grocery_product_photos as photos_module
from mealie.pkgs.safehttp.fetch import FetchResult
from mealie.schema.grocery.grocery import GroceryStore
from mealie.services.household_services.grocery_product_photos import (
    PhotoError,
    photo_in_page,
    save_sizes,
    store_photo_url,
)


def page(*, product_data: object = None, preload: list[str] | None = None, link_preview: str | None = None) -> str:
    """A store's product page, with the photo in the places stores put it"""
    head = []
    if link_preview:
        head.append(f'<meta property="og:image" content="{link_preview}">')
    for href in preload or []:
        head.append(f'<link rel="preload" as="image" href="{href}">')
    if product_data is not None:
        head.append(f'<script type="application/ld+json">{json.dumps(product_data)}</script>')
    return f"<html><head>{''.join(head)}</head><body><h1>A product</h1></body></html>"


WALMART_PHOTO = "https://i5.walmartimages.com/seo/Great-Value-Whole-Vitamin-D-Milk-Gallon_6a7b09b4.jpeg"
INSTACART = "https://d2lnr5mha7bycj.cloudfront.net/product-image/file"
ALDI_PLACEHOLDER = "https://d1s8987jlndkbs.cloudfront.net/assets/missing-item-4bbe82b8555e.png"
WHOLE_FOODS_LOGO = "https://m.media-amazon.com/images/S/assets.wholefoodsmarket.com/content/b5/68/wfm.png"


def test_walmart_shows_the_product_in_its_link_preview():
    html = page(link_preview=WALMART_PHOTO)
    assert photo_in_page(html, "https://www.walmart.com/ip/milk/10450114", GroceryStore.walmart) == WALMART_PHOTO


def test_cubs_product_data_has_the_photo_and_the_other_images_are_other_products():
    html = page(
        product_data={"@context": "https://schema.org", "@type": "Product", "image": [f"{INSTACART}/large_cub.png"]},
        preload=[f"{INSTACART}/large_related-1.jpg", f"{INSTACART}/large_related-2.jpg"],
    )
    url = "https://www.cub.com/store/cub/products/2793610-cub-milk-whole-1-gl"
    assert photo_in_page(html, url, GroceryStore.cub) == f"{INSTACART}/large_cub.png"


def test_aldis_product_data_has_a_placeholder_so_the_preloaded_photo_is_used():
    html = page(
        product_data={"@type": "Product", "image": [ALDI_PLACEHOLDER]},
        preload=["https://www.aldi.us/assets/logo.png", f"{INSTACART}/large_granola.jpg"],
    )
    url = "https://www.aldi.us/store/aldi/products/62750261-coconut-cacao-super-food-granola"
    assert photo_in_page(html, url, GroceryStore.aldi) == f"{INSTACART}/large_granola.jpg"


def test_whole_foods_link_preview_is_its_logo_so_only_the_product_data_counts():
    images = ["https://m.media-amazon.com/images/I/61m5EiZuUEL.jpg", "https://m.media-amazon.com/images/I/51y.jpg"]
    url = "https://www.wholefoodsmarket.com/grocery/product/organic-whole-milk-128-oz-b074h5sr5s"

    html = page(product_data={"@type": "Product", "image": images}, link_preview=WHOLE_FOODS_LOGO)
    assert photo_in_page(html, url, GroceryStore.whole_foods) == images[0]
    assert photo_in_page(page(link_preview=WHOLE_FOODS_LOGO), url, GroceryStore.whole_foods) is None


@pytest.mark.parametrize(
    "product_data",
    [
        {"@graph": [{"@type": "WebPage"}, {"@type": ["Product", "Thing"], "image": {"url": "/photos/milk.jpg"}}]},
        [{"@type": "BreadcrumbList"}, {"@type": "Product", "image": [{"contentUrl": "/photos/milk.jpg"}]}],
        {"@type": "WebPage", "mainEntity": {"@type": "Product", "image": "/photos/milk.jpg"}},
    ],
)
def test_product_data_is_found_however_its_nested(product_data: object):
    html = page(product_data=product_data)
    url = "https://www.cub.com/store/cub/products/1-milk"
    # and an address relative to the page is made whole
    assert photo_in_page(html, url, GroceryStore.cub) == "https://www.cub.com/photos/milk.jpg"


def test_photos_not_served_securely_and_broken_product_data_are_passed_over():
    html = '<script type="application/ld+json">{"@type": "Product", "image": </script>' + page(
        product_data={"@type": "Product", "image": ["http://cdn.example/milk.jpg", f"{INSTACART}/large_m.jpg"]}
    )
    url = "https://www.cub.com/store/cub/products/1-milk"
    assert photo_in_page(html, url, GroceryStore.cub) == f"{INSTACART}/large_m.jpg"


# =========================================================
# Fetching the store's page


def fetched(html: str, url: str = "https://www.walmart.com/ip/milk/10450114", status: int = 200) -> FetchResult:
    import httpx

    return FetchResult(content=html.encode(), status_code=status, url=url, headers=httpx.Headers(), encoding="utf-8")


class FakeStore:
    """The store's answers to each fetch, in turn: a page, None for turned away, or an exception to raise"""

    def __init__(self) -> None:
        self.answers: list = []
        self.requested: list[str] = []


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    fake = FakeStore()

    async def resilient_fetch(url: str, **_):
        fake.requested.append(url)
        answer = fake.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(photos_module, "resilient_fetch", resilient_fetch)
    return fake


@pytest.mark.asyncio
async def test_only_the_stores_pages_are_fetched(store: FakeStore):
    assert await store_photo_url("https://example.com/milk") is None
    assert await store_photo_url("https://walmart.com.example.net/ip/milk/1") is None
    assert store.requested == []


@pytest.mark.asyncio
async def test_a_robot_check_dressed_as_a_page_is_fetched_again(store: FakeStore):
    store.answers = [fetched("<html><title>Robot or human?</title></html>"), fetched(page(link_preview=WALMART_PHOTO))]
    assert await store_photo_url("https://www.walmart.com/ip/milk/10450114") == WALMART_PHOTO
    assert len(store.requested) == 2


@pytest.mark.asyncio
async def test_a_stalled_request_is_tried_again(store: FakeStore):
    store.answers = [TimeoutError(), fetched(page(link_preview=WALMART_PHOTO))]
    assert await store_photo_url("https://www.walmart.com/ip/milk/10450114") == WALMART_PHOTO


@pytest.mark.parametrize("answer", [None, fetched("Not found", status=404)])
@pytest.mark.asyncio
async def test_a_store_that_turns_every_request_away_isnt_asked_again(store: FakeStore, answer):
    store.answers = [answer]
    assert await store_photo_url("https://www.walmart.com/ip/milk/10450114") is None
    assert len(store.requested) == 1


@pytest.mark.asyncio
async def test_a_page_without_a_photo_is_given_up_on(store: FakeStore):
    store.answers = [fetched("<html></html>")] * 5
    assert await store_photo_url("https://www.walmart.com/ip/milk/10450114") is None
    assert len(store.requested) == photos_module.STORE_PAGE_TRIES


# =========================================================
# Keeping photos


def image_bytes(size: tuple[int, int], mode: str = "RGB", fmt: str = "JPEG", **save) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(buffer, fmt, **save)
    return buffer.getvalue()


def test_photos_are_kept_at_two_sizes_without_cropping(tmp_path: Path):
    save_sizes(image_bytes((1500, 3000)), tmp_path)

    with Image.open(tmp_path / "photo.webp") as photo, Image.open(tmp_path / "thumb.webp") as thumb:
        assert (photo.format, photo.size) == ("WEBP", (500, 1000))
        assert thumb.size == (160, 320)


def test_small_photos_arent_enlarged(tmp_path: Path):
    save_sizes(image_bytes((200, 100)), tmp_path)
    with Image.open(tmp_path / "photo.webp") as photo:
        assert photo.size == (200, 100)


def test_a_phone_photo_is_turned_upright(tmp_path: Path):
    exif = Image.Exif()
    exif[0x0112] = 6  # taken with the phone on its side
    save_sizes(image_bytes((400, 300), exif=exif), tmp_path)
    with Image.open(tmp_path / "photo.webp") as photo:
        assert photo.size == (300, 400)


def test_a_cut_out_product_keeps_its_transparency(tmp_path: Path):
    save_sizes(image_bytes((600, 600), mode="RGBA", fmt="PNG"), tmp_path)
    with Image.open(tmp_path / "thumb.webp") as thumb:
        assert thumb.mode == "RGBA"


@pytest.mark.parametrize("data", [b"<html>Robot or human?</html>", b"", image_bytes((50, 50))[:200]])
def test_what_isnt_a_photo_is_turned_down(tmp_path: Path, data: bytes):
    with pytest.raises(PhotoError):
        save_sizes(data, tmp_path / "photo")
    assert not (tmp_path / "photo").exists()


def test_enormous_images_arent_decoded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(photos_module, "MAX_PIXELS", 100 * 100)
    with pytest.raises(PhotoError, match="too large"):
        save_sizes(image_bytes((101, 100)), tmp_path)
