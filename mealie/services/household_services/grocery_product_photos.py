"""
Photos of the household's preferred products, so the shopping list shows the package to pick up.

A product's photo comes from the best place that has one:

- the store's own photo, from the product's page, for a product with a store link;
- the front of the package from Open Food Facts, for a product found by its barcode;
- a photo snapped of the package while scanning it, or one someone took or picked for the product.

Photos are found as soon as a link is pasted or a package scanned, before the product is saved, so the
form can show them. Until then a photo is a draft, kept under a random token for a day; saving the
product with it moves it into the product's own folder. Photos are copied rather than linked to: store
image links change, and every phone loading pictures from the stores' servers would be needless.
"""

import asyncio
import json
import os
import re
import secrets
import shutil
import time
from collections.abc import Iterator
from datetime import timedelta
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import UUID4

from mealie.core.config import get_app_dirs
from mealie.core.root_logger import get_logger
from mealie.pkgs.safehttp import resilient_fetch
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.grocery.grocery import (
    PHOTO_TOKEN_PATTERN,
    GroceryPhotoDraft,
    GroceryPhotoSource,
    GroceryProductOut,
    GroceryStore,
)

from .grocery_barcodes import look_up_barcode
from .grocery_product_links import store_for_url

logger = get_logger()


class PhotoSize(StrEnum):
    photo = "photo"
    """Shown large"""
    thumb = "thumb"
    """Shown in lists"""


LONGEST_SIDE = {PhotoSize.photo: 1000, PhotoSize.thumb: 320}

MAX_PAGE_BYTES = 6_000_000
MAX_IMAGE_BYTES = 15_000_000
MAX_PIXELS = 50_000_000
"""Images with more pixels than this are turned down rather than decoded"""

STORE_PAGE_BUDGET = 20
"""Seconds to spend getting a store's page, all tries together"""
STORE_PAGE_TRY = 10
STORE_PAGE_TRIES = 3
IMAGE_TIMEOUT = 10
DRAFT_LIFETIME = timedelta(days=1)

RANK = {
    GroceryPhotoSource.chosen: 3,
    GroceryPhotoSource.store: 2,
    GroceryPhotoSource.open_food_facts: 1,
    GroceryPhotoSource.scan: 1,
}
"""Which photos are better than which: a found photo only replaces a lower-ranked one by itself"""


class PhotoError(Exception):
    """A file that isn't a photo that can be used"""


class PhotoNotFoundError(Exception):
    """A draft photo that isn't there any more, or never was"""


# =========================================================
# Finding a store's photo of a product


class _Place(StrEnum):
    product_data = "product_data"
    """The page's schema.org Product data"""
    preloaded = "preloaded"
    """A product image the page has the browser load early"""
    link_preview = "link_preview"
    """The image a shared link shows (og:image)"""


# Each store keeps the photo somewhere else, and some of the places have the wrong photo
STORE_PHOTO_PLACES: dict[GroceryStore, tuple[_Place, ...]] = {
    # Walmart's link preview is the product
    GroceryStore.walmart: (_Place.link_preview, _Place.product_data),
    # Cub's and Aldi's shops run on Instacart. The product data has the photo, though Aldi's has a
    # placeholder instead, and the image the page loads early is the product's
    GroceryStore.cub: (_Place.product_data, _Place.preloaded),
    GroceryStore.aldi: (_Place.product_data, _Place.preloaded),
    # Whole Foods' link preview is its logo
    GroceryStore.whole_foods: (_Place.product_data,),
}
_PLACEHOLDERS = ("missing-item", "placeholder", "no-image", "noimage", "image-not-available", "image_not_available")


def _schema_products(data: Any) -> Iterator[dict]:
    """The schema.org Products in a page's structured data, wherever they're nested"""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(reversed(node))
        elif isinstance(node, dict):
            kind = node.get("@type")
            if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
                yield node
            stack.extend(value for value in node.values() if isinstance(value, dict | list))


def _image_urls(value: Any) -> Iterator[str]:
    """The addresses in a schema.org image: an address, an ImageObject, or a list of either"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("url", "contentUrl"):
            if isinstance(value.get(key), str):
                yield value[key]
    elif isinstance(value, list):
        for item in value:
            yield from _image_urls(item)


def _candidates(soup: BeautifulSoup, place: _Place) -> Iterator[str]:
    if place is _Place.product_data:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.get_text())
            except ValueError:
                continue
            for product in _schema_products(data):
                yield from _image_urls(product.get("image"))
    elif place is _Place.preloaded:
        for link in soup.find_all("link", rel="preload"):
            href = link.get("href")
            if link.get("as") == "image" and isinstance(href, str) and "/product-image/" in href:
                yield href
    elif place is _Place.link_preview:
        for meta in soup.find_all("meta", attrs={"property": "og:image"}):
            content = meta.get("content")
            if isinstance(content, str):
                yield content


def photo_in_page(html: str, page_url: str, store: GroceryStore) -> str | None:
    """The address of the product's photo on its page at a store, or None when the page doesn't show one"""

    soup = BeautifulSoup(html, "lxml")
    for place in STORE_PHOTO_PLACES.get(store, (_Place.product_data, _Place.preloaded)):
        for candidate in _candidates(soup, place):
            url = urljoin(page_url, candidate.strip())
            if url.startswith("https://") and not any(marker in url.lower() for marker in _PLACEHOLDERS):
                return url
    return None


async def store_photo_url(url: str) -> str | None:
    """
    The address of the store's photo of the product a link is for. Only the stores' own pages are
    fetched. Stores' robot checks come and go: one can stall a request, or answer with an ordinary-looking
    page that has no product in it, so a page without a photo is fetched again, with another browser's
    fingerprint, while there's time.
    """

    store = store_for_url(url)
    if store is None:
        return None

    deadline = time.monotonic() + STORE_PAGE_BUDGET
    for _ in range(STORE_PAGE_TRIES):
        remaining = deadline - time.monotonic()
        if remaining < 2:
            break
        try:
            page = await asyncio.wait_for(
                resilient_fetch(url, timeout=STORE_PAGE_TRY, allow_flaresolverr=False, max_bytes=MAX_PAGE_BYTES),
                timeout=min(STORE_PAGE_TRY, remaining),
            )
        except Exception as e:
            logger.debug(f"A try at the store's page for its photo failed: {type(e).__name__}")
            continue
        if page is None or page.status_code != 200:
            # turned away by every fingerprint, or there's no such page
            return None
        if photo := await asyncio.to_thread(photo_in_page, page.text, page.url, store):
            return photo
    return None


async def download_image(url: str) -> bytes | None:
    try:
        result = await asyncio.wait_for(
            resilient_fetch(url, timeout=IMAGE_TIMEOUT, allow_flaresolverr=False, max_bytes=MAX_IMAGE_BYTES),
            timeout=IMAGE_TIMEOUT,
        )
    except Exception as e:
        logger.warning(f"Couldn't download a product photo: {type(e).__name__}")
        return None
    if result is None or result.status_code != 200 or not result.content:
        return None
    return result.content


# =========================================================
# Keeping photos


def save_sizes(image: Path | bytes, folder: Path) -> None:
    """Saves an image in each size, upright, as WebP files in `folder`, or raises PhotoError"""

    try:
        with Image.open(image if isinstance(image, Path) else BytesIO(image)) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise PhotoError("That photo is too large")
            picture = ImageOps.exif_transpose(opened)
            alpha = picture.mode in ("RGBA", "LA", "PA") or (picture.mode == "P" and "transparency" in picture.info)
            picture = picture.convert("RGBA" if alpha else "RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as e:
        raise PhotoError("That isn't a photo Mealie can read") from e

    folder.mkdir(parents=True, exist_ok=True)
    for size, side in LONGEST_SIDE.items():
        copy = picture.copy()
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)
        copy.save(folder / f"{size.value}.webp", "WEBP", quality=82, method=4)


def photos_folder() -> Path:
    return get_app_dirs().DATA_DIR / "groceries"


def purge_old_drafts(folder: Path) -> None:
    """Removes the draft photos in a household's folder that are older than a day"""
    cutoff = time.time() - DRAFT_LIFETIME.total_seconds()
    for draft in folder.iterdir():
        try:
            if draft.stat().st_mtime < cutoff:
                shutil.rmtree(draft, ignore_errors=True)
        except FileNotFoundError:
            pass


class GroceryProductPhotos:
    def __init__(self, repos: AllRepositories) -> None:
        self.repos = repos
        self.root = photos_folder()

    # =========================================================
    # Drafts

    def _draft_folder(self, token: str) -> Path:
        if not re.fullmatch(PHOTO_TOKEN_PATTERN, token):
            raise PhotoNotFoundError()
        return self.root / "drafts" / str(self.repos.household_id) / token

    def draft(self, image: Path | bytes, source: GroceryPhotoSource) -> GroceryPhotoDraft:
        """Keeps an image as a draft photo, or raises PhotoError"""

        token = secrets.token_hex(16)
        folder = self._draft_folder(token)
        try:
            save_sizes(image, folder)
            (folder / "source").write_text(source.value)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        purge_old_drafts(folder.parent)
        return GroceryPhotoDraft(token=token, source=source)

    def draft_file(self, token: str, size: PhotoSize) -> Path | None:
        try:
            path = self._draft_folder(token) / f"{size.value}.webp"
        except PhotoNotFoundError:
            return None
        return path if path.is_file() else None

    async def _draft_from(self, url: str, source: GroceryPhotoSource) -> GroceryPhotoDraft | None:
        image = await download_image(url)
        if image is None:
            return None
        try:
            return await asyncio.to_thread(self.draft, image, source)
        except PhotoError:
            logger.warning(f"A product photo from {source.value} couldn't be read")
            return None

    # =========================================================
    # Finding a photo

    async def from_store(self, url: str) -> GroceryPhotoDraft | None:
        """The store's photo of the product a link is for"""
        try:
            photo = await store_photo_url(url)
            return await self._draft_from(photo, GroceryPhotoSource.store) if photo else None
        except Exception:
            logger.exception("Couldn't get a store's photo of a product")
            return None

    async def from_open_food_facts(self, image_url: str) -> GroceryPhotoDraft | None:
        """Open Food Facts' photo of the front of a package"""
        try:
            return await self._draft_from(image_url, GroceryPhotoSource.open_food_facts)
        except Exception:
            logger.exception("Couldn't get a product photo from Open Food Facts")
            return None

    async def find(self, url: str | None = None, barcode: str | None = None) -> GroceryPhotoDraft | None:
        """The best photo to be had: the store's for a store link, otherwise Open Food Facts' for a barcode"""

        if url and (photo := await self.from_store(url)):
            return photo
        if barcode and (packaged := await look_up_barcode(barcode)) and packaged.image_url:
            return await self.from_open_food_facts(packaged.image_url)
        return None

    # =========================================================
    # Products' photos

    def product_folder(self, product_id: UUID4) -> Path:
        return self.root / "products" / str(product_id)

    def product_file(self, product: GroceryProductOut, size: PhotoSize) -> Path | None:
        if not product.photo:
            return None
        path = self.product_folder(product.id) / f"{size.value}.webp"
        return path if path.is_file() else None

    def attach(self, product: GroceryProductOut, token: str) -> GroceryProductOut:
        """Makes a draft photo the product's photo, or raises PhotoNotFoundError"""

        draft = self._draft_folder(token)
        try:
            source = GroceryPhotoSource((draft / "source").read_text().strip())
        except (FileNotFoundError, ValueError) as e:
            raise PhotoNotFoundError() from e

        folder = self.product_folder(product.id)
        shutil.rmtree(folder, ignore_errors=True)
        folder.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(draft, folder)
        (folder / "source").unlink(missing_ok=True)
        # the folder is new as far as clearing out the photos of deleted products goes
        os.utime(folder)
        return self.repos.grocery_products.patch(product.id, {"photo": secrets.token_hex(4), "photo_source": source})

    def remove(self, product: GroceryProductOut) -> GroceryProductOut:
        self.delete(product.id)
        return self.repos.grocery_products.patch(product.id, {"photo": None, "photo_source": None})

    def delete(self, product_id: UUID4) -> None:
        shutil.rmtree(self.product_folder(product_id), ignore_errors=True)
