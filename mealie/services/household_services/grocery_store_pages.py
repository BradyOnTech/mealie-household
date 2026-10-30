"""
Finding a scanned product's own page at its store, so it gets the store's link and photo just as a pasted
link would.

Stores don't answer a server's searches: Walmart's search shows robots a check, and Cub's, Aldi's and Whole
Foods' results are put together in the shopper's browser. Their product pages open fine, though. So the
household's AI searches the web for the product's page (only ChatGPT providers can, with Codex's own search),
and each page it names is opened and checked before it's believed: the page has to carry the barcode, or name
the same brand, product and size.

Searches are shared. A product scanned in the form and saved before its page turns up is waited on rather than
looked for twice, and an answer is kept for a while, found or not.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pydantic import UUID4

from mealie.core.root_logger import get_logger
from mealie.db.db_setup import session_context
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.grocery.grocery import GroceryPhotoSource, GroceryStore, GroceryUnit
from mealie.schema.group.ai_providers import AITask
from mealie.schema.openai.grocery_store_page import OpenAIStoreProductPages
from mealie.services.openai import OpenAIService

from .grocery_barcodes import look_up_barcode
from .grocery_product_links import PackageSize, name_similarity, name_words, package_size, store_for_url
from .grocery_product_photos import (
    RANK,
    GroceryProductPhotos,
    ProductPage,
    download_image,
    fetch_product_page,
    schema_products,
)

logger = get_logger()

TASK = AITask.ingredient_parsing
"""Finding a product is the same kind of request as reading one, so it runs on the same provider and model"""

AI_SEARCH_TIMEOUT = 90
MAX_CANDIDATES = 3
FOUND_LIFETIME = 24 * 3600
NOT_FOUND_LIFETIME = 6 * 3600
FAILED_LIFETIME = 10 * 60
"""How long an answer is kept, in seconds: a page that was found, none, or a search that failed"""
MAX_KEPT = 500


@dataclass(frozen=True)
class StoreSite:
    name: str
    host: str
    example: str
    """What its product pages' addresses look like, for the AI to recognize them by"""
    product_path: re.Pattern[str]


STORE_SITES: dict[GroceryStore, StoreSite] = {
    GroceryStore.walmart: StoreSite(
        "Walmart", "walmart.com", "https://www.walmart.com/ip/<name>/<number>", re.compile(r"^/ip/")
    ),
    GroceryStore.cub: StoreSite(
        "Cub Foods",
        "cub.com",
        "https://www.cub.com/store/cub/products/<number>-<name>",
        re.compile(r"^/(store/cub/products|product)/"),
    ),
    GroceryStore.aldi: StoreSite(
        "Aldi",
        "aldi.us",
        "https://www.aldi.us/store/aldi/products/<number>-<name>",
        re.compile(r"^/store/aldi/products/"),
    ),
    GroceryStore.whole_foods: StoreSite(
        "Whole Foods Market",
        "wholefoodsmarket.com",
        "https://www.wholefoodsmarket.com/grocery/product/<name>-<code>",
        re.compile(r"^/(grocery/)?product/"),
    ),
}


@dataclass
class ScannedProduct:
    """What's known about a scanned product, to tell its page from another's"""

    barcode: str
    names: list[str] = field(default_factory=list)
    brand: str = ""
    size: PackageSize | None = None


@dataclass
class StorePage:
    url: str
    photo: str


class SearchFailedError(Exception):
    """The AI couldn't search, which is worth trying again sooner than a search that found nothing"""


# =========================================================
# Telling the product's page from others


def is_product_page(url: str, store: GroceryStore) -> bool:
    """Whether an address is one of the store's product pages"""
    site = STORE_SITES.get(store)
    parts = urlsplit(url)
    return bool(
        site and parts.scheme == "https" and store_for_url(url) == store and site.product_path.match(parts.path)
    )


_TITLE_NOISE = re.compile(r"\s*(same-day delivery or pickup|delivery or pickup near me|- walmart\.com)\s*$", re.I)


def page_product_name(html: str) -> str:
    """The product's name as its page gives it"""

    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for product in schema_products(data):
            if isinstance(name := product.get("name"), str) and name.strip():
                return name.strip()
    meta = soup.find("meta", attrs={"property": "og:title"})
    content = meta.get("content") if meta else None
    title = content if isinstance(content, str) else soup.title.get_text() if soup.title else ""
    return _TITLE_NOISE.sub("", title.split("|")[0]).strip()


def carries_barcode(html: str, barcode: str) -> bool:
    """Whether a page has the barcode in it, with or without its leading zeros"""
    digits = barcode.lstrip("0")
    return len(digits) >= 7 and re.search(rf"(?<!\d)0*{digits}(?!\d)", html) is not None


# the same amount in different units: grams for weights, milliliters for volumes
_MEASURES: dict[GroceryUnit, tuple[str, float]] = {
    GroceryUnit.gram: ("weight", 1),
    GroceryUnit.kilogram: ("weight", 1000),
    GroceryUnit.ounce: ("weight", 28.3495),
    GroceryUnit.pound: ("weight", 453.592),
    GroceryUnit.milliliter: ("volume", 1),
    GroceryUnit.liter: ("volume", 1000),
    GroceryUnit.fluid_ounce: ("volume", 29.5735),
    GroceryUnit.cup: ("volume", 236.588),
    GroceryUnit.COUNT: ("count", 1),
}


def sizes_agree(first: PackageSize | None, second: PackageSize | None) -> bool:
    """Whether two package sizes could be the same, which they always could when either isn't known"""
    if first is None or second is None:
        return True
    (kind, factor), (other_kind, other_factor) = _MEASURES[first.unit], _MEASURES[second.unit]
    if kind != other_kind:
        # "oz" is a weight to some and a volume to others, so this says nothing
        return True
    a, b = first.quantity * factor, second.quantity * other_factor
    return abs(a - b) <= 0.05 * max(a, b)


def page_is_product(html: str, product: ScannedProduct) -> bool:
    """
    Whether a store's page is the scanned product's. The barcode settles it, unless the page is plainly some
    other product that only mentions it. Without it, the page has to name the same brand and product, at the
    same size where both say.
    """

    name = page_product_name(html)
    similarity = max((name_similarity(name, known) for known in product.names), default=0.0)
    brand = name_words(product.brand)
    brand_named = bool(brand & name_words(name))
    if carries_barcode(html, product.barcode):
        return brand_named or similarity >= 0.34
    sized = sizes_agree(package_size(name), product.size)
    if brand:
        return brand_named and similarity >= 0.5 and sized
    return similarity >= 0.6 and sized


# =========================================================
# Searching


def _size_text(size: PackageSize | None) -> str:
    units = {GroceryUnit.fluid_ounce: "fl oz", GroceryUnit.ounce: "oz", GroceryUnit.COUNT: "count"}
    return f"{size.quantity:g} {units.get(size.unit, size.unit.value)}" if size else "unknown"


async def _ask_ai(group_id: UUID4, household_id: UUID4, store: GroceryStore, product: ScannedProduct) -> list[str]:
    """The addresses the household's AI finds for the product's page, best first"""

    site = STORE_SITES[store]
    message = "\n".join(
        [
            f"Store: {site.name} ({site.host})",
            f"Its product pages look like: {site.example}",
            f"Product: {product.names[0]}",
            f"Brand: {product.brand or 'unknown'}",
            f"Package size: {_size_text(product.size)}",
            f"Barcode: {product.barcode}",
        ]
    )
    # a session of its own, since a search can outlast the request that started it
    with session_context() as session:
        ai = OpenAIService(get_repositories(session, group_id=group_id, household_id=household_id))
        try:
            response = await asyncio.wait_for(
                ai.get_response(
                    ai.get_prompt("household.find-store-product-page"),
                    message,
                    response_schema=OpenAIStoreProductPages,
                    task=TASK,
                    web_search=True,
                ),
                timeout=AI_SEARCH_TIMEOUT,
            )
        except Exception as e:
            raise SearchFailedError() from e
    return [url.strip() for url in (response.urls if response else [])][:MAX_CANDIDATES]


async def search_store(
    group_id: UUID4, household_id: UUID4, barcode: str, store: GroceryStore, name: str = ""
) -> StorePage | None:
    """The product's page at the store, checked to be it, or None when it can't be found"""

    packaged = await look_up_barcode(barcode)
    product = ScannedProduct(
        barcode=barcode,
        names=[known for known in (packaged.listing if packaged else "", name.strip()) if known],
        brand=packaged.brand if packaged else "",
        size=(packaged.size if packaged else None) or package_size(name),
    )
    if not product.names:
        return None

    for url in await _ask_ai(group_id, household_id, store, product):
        if not is_product_page(url, store):
            continue
        page: ProductPage | None = await fetch_product_page(url)
        if page and is_product_page(page.url, store) and await asyncio.to_thread(page_is_product, page.html, product):
            return StorePage(url=page.url, photo=page.photo)
        logger.debug("The AI named a store page that isn't the scanned product's")
    return None


_searches: dict[tuple[str, GroceryStore], tuple[float, asyncio.Task[StorePage | None]]] = {}


def _lifetime(task: asyncio.Task[StorePage | None]) -> float:
    if not task.done():
        return float("inf")
    if task.cancelled() or task.exception():
        return FAILED_LIFETIME
    return FOUND_LIFETIME if task.result() else NOT_FOUND_LIFETIME


def _forget_old(now: float) -> None:
    for key, (started, task) in list(_searches.items()):
        if now - started > _lifetime(task):
            del _searches[key]
    while len(_searches) > MAX_KEPT:
        del _searches[min(_searches, key=lambda key: _searches[key][0])]


class StorePageFinder:
    def __init__(self, repos: AllRepositories, ai: OpenAIService | None = None) -> None:
        self.repos = repos
        self.ai = ai if ai is not None else OpenAIService(repos)

    @property
    def available(self) -> bool:
        """Whether the household's AI can search the web for pages"""
        return self.ai.can_search_web(TASK)

    async def find(self, barcode: str, store: GroceryStore, name: str = "") -> StorePage | None:
        """A product's page at a store, from its barcode: shared with a search for it already under way"""

        if store not in STORE_SITES or not self.available or not self.repos.group_id or not self.repos.household_id:
            return None
        key, now = (barcode, store), time.monotonic()
        kept = _searches.get(key)
        if kept is None or now - kept[0] > _lifetime(kept[1]):
            task = asyncio.create_task(search_store(self.repos.group_id, self.repos.household_id, barcode, store, name))
            # a search nobody waits for any more still finishes; its failure shouldn't go unremarked
            task.add_done_callback(lambda done: done.cancelled() or done.exception())
            _searches[key] = (now, task)
            _forget_old(now)
        else:
            task = kept[1]
        try:
            return await asyncio.shield(task)
        except SearchFailedError:
            logger.warning("The household's AI couldn't search for a product's page at its store")
        except Exception:
            logger.exception("Looking for a product's page at its store failed")
        return None


async def fill_in_from_store(group_id: UUID4, household_id: UUID4, product_id: UUID4) -> None:
    """
    After a product is saved with a barcode but no store link: finds its page at its store, and saves the link
    and the store's photo with it. A link someone gave, or a photo someone chose, is never replaced.
    """

    try:
        with session_context() as session:
            repos = get_repositories(session, group_id=group_id, household_id=household_id)
            product = repos.grocery_products.get_one(product_id)
            if product is None or product.url or not product.barcode:
                return
            store = product.store
            page = await StorePageFinder(repos).find(product.barcode, store, product.name)
            if page is None:
                return

            # the product may have changed, or gone, while its page was looked for
            session.expire_all()
            product = repos.grocery_products.get_one(product_id)
            if product is None or product.url or product.store != store:
                return
            product = repos.grocery_products.patch(product_id, {"url": page.url})
            current = RANK[product.photo_source] if product.photo_source else 0
            if RANK[GroceryPhotoSource.store] <= current:
                return
            image = await download_image(page.photo)
            if image:
                photos = GroceryProductPhotos(repos)
                draft = await asyncio.to_thread(photos.draft, image, GroceryPhotoSource.store)
                photos.attach(product, draft.token)
    except Exception:
        logger.exception("Couldn't fill in a product's store link and photo")
