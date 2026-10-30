"""Finding a scanned product's page at its store, and telling it from other products' pages."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

import mealie.services.household_services.grocery_store_pages as store_pages
from mealie.schema.grocery.grocery import GroceryStore, GroceryUnit
from mealie.services.household_services.grocery_barcodes import PackagedProduct
from mealie.services.household_services.grocery_product_links import PackageSize
from mealie.services.household_services.grocery_product_photos import ProductPage
from mealie.services.household_services.grocery_store_pages import (
    ScannedProduct,
    StorePage,
    StorePageFinder,
    carries_barcode,
    is_product_page,
    page_is_product,
    page_product_name,
    search_store,
    sizes_agree,
)

GRANOLA = ScannedProduct(
    barcode="4061462608377",
    names=["Millville Coconut Cacao Granola 11 oz"],
    brand="Millville",
    size=PackageSize(11, GroceryUnit.ounce),
)
MILK = ScannedProduct(
    barcode="0078742351865",
    names=["Great Value Whole Milk 1 gallon"],
    brand="Great Value",
    size=PackageSize(128, GroceryUnit.fluid_ounce),
)


def html(title: str = "", *, name: str | None = None, body: str = "") -> str:
    product = f'<script type="application/ld+json">{json.dumps({"@type": "Product", "name": name})}</script>'
    return f"<html><head><title>{title}</title>{product if name else ''}</head><body>{body}</body></html>"


@pytest.fixture(autouse=True)
def forget_searches():
    store_pages._searches.clear()
    yield
    store_pages._searches.clear()


@pytest.mark.parametrize(
    ("url", "store", "expected"),
    [
        ("https://www.walmart.com/ip/Great-Value-Whole-Milk/10450114", GroceryStore.walmart, True),
        ("https://www.walmart.com/ip/10450114", GroceryStore.walmart, True),
        ("https://www.walmart.com/search?q=milk", GroceryStore.walmart, False),
        ("https://www.aldi.us/store/aldi/products/62750261-coconut-cacao-super-food-granola", GroceryStore.aldi, True),
        ("https://www.aldi.us/store/aldi/s?k=granola", GroceryStore.aldi, False),
        ("https://www.cub.com/store/cub/products/2793610-cub-milk-whole-1-gl", GroceryStore.cub, True),
        ("https://www.cub.com/product/cub-whole-milk-id-00041130470066", GroceryStore.cub, True),
        (
            "https://www.wholefoodsmarket.com/grocery/product/365-organic-whole-milk-b074h5sr5s",
            GroceryStore.whole_foods,
            True,
        ),
        # another store's page, a lookalike host, and an insecure address aren't
        ("https://www.walmart.com/ip/Great-Value-Whole-Milk/10450114", GroceryStore.cub, False),
        ("https://walmart.com.example.net/ip/milk/1", GroceryStore.walmart, False),
        ("http://www.walmart.com/ip/milk/10450114", GroceryStore.walmart, False),
    ],
)
def test_only_the_stores_product_pages_count(url: str, store: GroceryStore, expected: bool):
    assert is_product_page(url, store) is expected


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (
            html("Millville Gluten Free Coconut Cacao Superfood Granola Same-Day Delivery or Pickup | ALDI"),
            "Millville Gluten Free Coconut Cacao Superfood Granola",
        ),
        (html("Cub Milk, Whole Same-Day Delivery or Pickup | Cub"), "Cub Milk, Whole"),
        (
            html("Great Value Whole Vitamin D Milk Gallon 128 Fl Oz - Walmart.com"),
            "Great Value Whole Vitamin D Milk Gallon 128 Fl Oz",
        ),
        (
            html("Grocery | Whole Foods Market", name="365 by Whole Foods Market, Organic Whole Milk, 128 Fl Oz"),
            "365 by Whole Foods Market, Organic Whole Milk, 128 Fl Oz",
        ),
    ],
)
def test_a_pages_product_name_is_read_without_the_stores_additions(page: str, expected: str):
    assert page_product_name(page) == expected


def test_a_barcode_is_found_with_or_without_its_leading_zeros_but_not_inside_a_longer_number():
    assert carries_barcode('{"upc":"078742351865"}', "0078742351865")
    assert carries_barcode("gtin 00078742351865", "0078742351865")
    assert not carries_barcode("item 1078742351865", "0078742351865")
    assert not carries_barcode("item 0787423518650", "0078742351865")


@pytest.mark.parametrize(
    ("first", "second", "agree"),
    [
        (PackageSize(11, GroceryUnit.ounce), PackageSize(312, GroceryUnit.gram), True),
        (PackageSize(128, GroceryUnit.fluid_ounce), PackageSize(3.785, GroceryUnit.liter), True),
        (PackageSize(11, GroceryUnit.ounce), PackageSize(14, GroceryUnit.ounce), False),
        # "oz" means a weight to some and a volume to others
        (PackageSize(64, GroceryUnit.ounce), PackageSize(64, GroceryUnit.fluid_ounce), True),
        (PackageSize(11, GroceryUnit.ounce), None, True),
    ],
)
def test_package_sizes_are_compared_across_units(first: PackageSize, second: PackageSize | None, agree: bool):
    assert sizes_agree(first, second) is agree


def test_a_page_carrying_the_barcode_is_the_product():
    page = html("Great Value Whole Vitamin D Milk Gallon 128 Fl Oz - Walmart.com", body='"upc":"078742351865"')
    assert page_is_product(page, MILK)


def test_a_page_that_only_mentions_the_barcode_is_not():
    """Another product's page can list this one among its related products"""
    page = html("Kemps Select 2% Reduced Fat Milk - Walmart.com", body='"upc":"078742351865"')
    assert not page_is_product(page, MILK)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Millville Gluten Free Coconut Cacao Superfood Granola Same-Day Delivery or Pickup | ALDI", True),
        ("Millville Coconut Cacao Super Food Granola, 11 oz Same-Day Delivery or Pickup | ALDI", True),
        # another brand's, and the same granola in another size
        ("Simply Nature Coconut Cacao Granola Same-Day Delivery or Pickup | ALDI", False),
        ("Millville Coconut Cacao Granola, 14 oz Same-Day Delivery or Pickup | ALDI", False),
        ("Millville Oats & Honey Granola Same-Day Delivery or Pickup | ALDI", False),
    ],
)
def test_without_the_barcode_a_page_must_name_the_same_brand_product_and_size(title: str, expected: bool):
    assert page_is_product(html(title), GRANOLA) is expected


# =========================================================
# Searching


def product_page(url: str, title: str, body: str = "") -> ProductPage:
    return ProductPage(url=url, html=html(title, body=body), photo=f"{url}/photo.jpg")


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):
    """The AI's answer, and the store pages there are"""
    found = SimpleNamespace(urls=[], pages={}, asked=[])

    async def ask_ai(group_id, household_id, store, product):
        found.asked.append((store, product))
        return found.urls

    async def fetch_product_page(url: str):
        return found.pages.get(url)

    async def look_up_barcode(barcode: str):
        return PackagedProduct(
            barcode=barcode,
            name="Coconut Cacao Granola",
            brand="Millville",
            quantity="11 oz",
            size=PackageSize(11, GroceryUnit.ounce),
        )

    monkeypatch.setattr(store_pages, "_ask_ai", ask_ai)
    monkeypatch.setattr(store_pages, "fetch_product_page", fetch_product_page)
    monkeypatch.setattr(store_pages, "look_up_barcode", look_up_barcode)
    return found


ALDI_PAGE = "https://www.aldi.us/store/aldi/products/62750261-coconut-cacao-super-food-granola"


@pytest.mark.asyncio
async def test_the_first_page_that_checks_out_is_the_one(web):
    other = "https://www.aldi.us/store/aldi/products/1-millville-oats-honey-granola"
    web.urls = ["https://www.aldi.us/store/aldi/s?k=granola", other, ALDI_PAGE]
    web.pages = {
        other: product_page(other, "Millville Oats & Honey Granola | ALDI"),
        ALDI_PAGE: product_page(ALDI_PAGE, "Millville Gluten Free Coconut Cacao Superfood Granola | ALDI"),
    }

    page = await search_store(uuid4(), uuid4(), GRANOLA.barcode, GroceryStore.aldi, "Coconut cacao granola")

    assert page == StorePage(url=ALDI_PAGE, photo=f"{ALDI_PAGE}/photo.jpg")
    store, product = web.asked[0]
    assert store is GroceryStore.aldi
    assert product.brand == "Millville"


@pytest.mark.asyncio
async def test_no_page_that_checks_out_is_none(web):
    web.urls = [ALDI_PAGE]
    web.pages = {ALDI_PAGE: product_page(ALDI_PAGE, "Simply Nature Coconut Cacao Granola | ALDI")}
    assert await search_store(uuid4(), uuid4(), GRANOLA.barcode, GroceryStore.aldi) is None


def finder(can_search: bool = True) -> StorePageFinder:
    repos = SimpleNamespace(group_id=uuid4(), household_id=uuid4())
    return StorePageFinder(repos, ai=SimpleNamespace(can_search_web=lambda task: can_search))  # type: ignore[arg-type]


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    started: list[str] = []

    async def search(group_id, household_id, barcode, store, name=""):
        started.append(barcode)
        await asyncio.sleep(0.05)
        return StorePage(url=ALDI_PAGE, photo=f"{ALDI_PAGE}/photo.jpg") if barcode == GRANOLA.barcode else None

    monkeypatch.setattr(store_pages, "search_store", search)
    return started


@pytest.mark.asyncio
async def test_searches_for_the_same_product_are_shared_and_kept(searches: list[str]):
    first, second = await asyncio.gather(
        finder().find(GRANOLA.barcode, GroceryStore.aldi), finder().find(GRANOLA.barcode, GroceryStore.aldi)
    )
    again = await finder().find(GRANOLA.barcode, GroceryStore.aldi)
    nothing = [await finder().find("0041483022011", GroceryStore.aldi) for _ in range(2)]

    assert first == second == again
    assert first is not None
    assert nothing == [None, None]
    # one search each, found or not
    assert searches == [GRANOLA.barcode, "0041483022011"]


@pytest.mark.asyncio
async def test_nothing_is_searched_without_an_ai_that_searches_the_web(searches: list[str]):
    assert await finder(can_search=False).find(GRANOLA.barcode, GroceryStore.aldi) is None
    assert searches == []


@pytest.mark.asyncio
async def test_a_failed_search_is_none_and_kept_only_briefly(monkeypatch: pytest.MonkeyPatch):
    async def search(*args, **kwargs):
        raise store_pages.SearchFailedError()

    monkeypatch.setattr(store_pages, "search_store", search)
    assert await finder().find(GRANOLA.barcode, GroceryStore.aldi) is None
    _, task = store_pages._searches[(GRANOLA.barcode, GroceryStore.aldi)]
    assert store_pages._lifetime(task) == store_pages.FAILED_LIFETIME
