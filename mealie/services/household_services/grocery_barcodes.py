"""
Barcodes on grocery packages, and what they say about the product.

US packages carry a UPC-A (12 digits), or on small packages its short form UPC-E (8); elsewhere it's an
EAN-13 or EAN-8. All end in a check digit. A scanner can read the same package as a UPC-A or as the
EAN-13 that's the UPC with a leading zero, so codes are kept as 13 digits where they fit, and the two
readings match.

What a barcode doesn't say, Open Food Facts usually does: a free, open database of packaged food that
knows the store brands here too (Great Value, Cub, Friendly Farms, 365).
"""

import json
import re
from dataclasses import dataclass, field

from mealie.core.root_logger import get_logger
from mealie.pkgs.safehttp import resilient_fetch
from mealie.schema.grocery.grocery import GroceryStore, GroceryUnit

from .grocery_product_links import PackageSize, package_size

logger = get_logger()

OPEN_FOOD_FACTS_URL = (
    "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    "?fields=code,product_name,product_name_en,generic_name_en,brands,quantity,product_quantity,"
    "product_quantity_unit,categories_tags,image_front_url"
)
LOOKUP_TIMEOUT_SECONDS = 8


def _check_digit_ok(digits: str) -> bool:
    """The GS1 check: digits weighted 3, 1, 3, ... from the right, check digit excluded"""
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == int(digits[-1])


def expand_upce(digits: str) -> str | None:
    """The UPC-A a UPC-E stands for. A UPC-E drops zeros from its UPC-A by rules set by its sixth digit."""

    if len(digits) != 8 or digits[0] not in "01":
        return None
    system, code, check = digits[0], digits[1:7], digits[7]
    last = code[5]
    if last in "012":
        body = f"{code[0:2]}{last}0000{code[2:5]}"
    elif last == "3":
        body = f"{code[0:3]}00000{code[3:5]}"
    elif last == "4":
        body = f"{code[0:4]}00000{code[4]}"
    else:
        body = f"{code[0:5]}0000{last}"
    return f"{system}{body}{check}"


def normalize_barcode(value: str | None, kind: str | None = None) -> str | None:
    """
    A package barcode in the form products are saved with, or None when it isn't a valid one. `kind` is
    the format a scanner reported, which tells a UPC-E from an EAN-8 (both are eight digits).
    """

    digits = re.sub(r"\D", "", value or "")
    reported = re.sub(r"[^a-z0-9]", "", (kind or "").lower())
    if len(digits) == 8 and (reported == "upce" or (not reported and not _check_digit_ok(digits))):
        digits = expand_upce(digits) or digits
    if len(digits) not in (8, 12, 13, 14) or not _check_digit_ok(digits):
        return None
    if len(digits) == 12:
        digits = f"0{digits}"
    elif len(digits) == 14 and digits.startswith("0"):
        digits = digits[1:]
    return digits


# Each store's own brands, which are only sold there
STORE_BRANDS: dict[GroceryStore, tuple[str, ...]] = {
    GroceryStore.walmart: (
        "great value",
        "marketside",
        "freshness guaranteed",
        "sam's choice",
        "bettergoods",
        "equate",
        "parent's choice",
        "walmart",
    ),
    GroceryStore.aldi: (
        "friendly farms",
        "simply nature",
        "happy farms",
        "millville",
        "clancy's",
        "specially selected",
        "southern grove",
        "baker's corner",
        "barissimo",
        "kirkwood",
        "appleton farms",
        "l'oven fresh",
        "season's choice",
        "stonemill",
        "fit & active",
        "casa mamita",
        "chef's cupboard",
        "burman's",
        "reggano",
        "carlini",
        "sundae shoppe",
        "park street deli",
        "lunch mate",
        "emporium selection",
        "little salad bar",
        "benton's",
        "nature's nectar",
        "tuscan garden",
        "earth grown",
        "mama cozzi's",
        "aldi",
    ),
    GroceryStore.whole_foods: ("365", "whole foods market", "whole foods"),
    GroceryStore.cub: ("cub", "cub foods", "essential everyday", "wild harvest", "shoppers value", "culinary tours"),
}


def _brand_words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9&']+", text.lower().replace("’", "'")))


def store_for_brand(brands: str | None) -> GroceryStore | None:
    """The store a store brand is sold at, like Walmart for Great Value, or None for a national brand"""

    for brand in (brands or "").split(","):
        words = f" {_brand_words(brand)} "
        for store, names in STORE_BRANDS.items():
            if any(f" {name} " in words for name in names):
                return store
    return None


# How Open Food Facts gives an amount, and the unit the grocery list counts it in
_FOOD_FACTS_UNITS = {
    "g": GroceryUnit.gram,
    "kg": GroceryUnit.kilogram,
    "ml": GroceryUnit.milliliter,
    "l": GroceryUnit.liter,
    "oz": GroceryUnit.ounce,
    "lb": GroceryUnit.pound,
    "fl oz": GroceryUnit.fluid_ounce,
}


@dataclass
class PackagedProduct:
    """What Open Food Facts knows about a barcode's product"""

    barcode: str
    name: str
    brand: str = ""
    quantity: str = ""
    """As the package prints it, e.g. "1 gallon" """
    categories: list[str] = field(default_factory=list)
    """Most general first, e.g. ["dairies", "milks", "whole milks"]"""
    size: PackageSize | None = None
    image_url: str | None = None
    """A photo of the front of the package"""

    @property
    def listing(self) -> str:
        """The product as a store would list it, e.g. "Great Value Whole Milk 1 gallon" """
        name = self.name if not self.brand or self.brand.lower() in self.name.lower() else f"{self.brand} {self.name}"
        return f"{name} {self.quantity}".strip()


def _food_facts_size(product: dict) -> PackageSize | None:
    if size := package_size(str(product.get("quantity") or "")):
        return size
    unit = _FOOD_FACTS_UNITS.get(str(product.get("product_quantity_unit") or "").lower())
    try:
        amount = float(product.get("product_quantity") or 0)
    except TypeError, ValueError:
        return None
    return PackageSize(round(amount, 3), unit) if unit and amount > 0 else None


def _https_url(value: object) -> str | None:
    return value if isinstance(value, str) and value.startswith("https://") else None


def parse_food_facts(barcode: str, data: dict) -> PackagedProduct | None:
    """A product from an Open Food Facts reply, or None when it doesn't know the product's name"""

    product = data.get("product") if data.get("status") == 1 else None
    if not isinstance(product, dict):
        return None
    name = next(
        (
            str(value).strip()
            for value in (product.get("product_name_en"), product.get("product_name"), product.get("generic_name_en"))
            if value and str(value).strip()
        ),
        "",
    )
    if not name:
        return None
    categories = [
        tag.split(":", 1)[-1].replace("-", " ")
        for tag in product.get("categories_tags") or []
        if isinstance(tag, str) and tag.startswith("en:")
    ]
    return PackagedProduct(
        barcode=barcode,
        name=name,
        brand=str(product.get("brands") or "").split(",")[0].strip(),
        quantity=str(product.get("quantity") or "").strip(),
        categories=categories,
        size=_food_facts_size(product),
        image_url=_https_url(product.get("image_front_url")),
    )


async def look_up_barcode(barcode: str) -> PackagedProduct | None:
    """What Open Food Facts knows about a barcode, or None when it doesn't know it or can't be reached"""

    try:
        result = await resilient_fetch(
            OPEN_FOOD_FACTS_URL.format(barcode=barcode),
            timeout=LOOKUP_TIMEOUT_SECONDS,
            allow_flaresolverr=False,
            max_bytes=1_000_000,
        )
        if result is None or result.status_code != 200:
            return None
        return parse_food_facts(barcode, json.loads(result.text))
    except Exception:
        logger.exception("Couldn't look up a barcode in Open Food Facts")
        return None
