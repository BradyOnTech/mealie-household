import pytest

from mealie.schema.grocery.grocery import GroceryStore, GroceryUnit
from mealie.services.household_services.grocery_barcodes import (
    PackagedProduct,
    expand_upce,
    normalize_barcode,
    parse_food_facts,
    store_for_brand,
)
from mealie.services.household_services.grocery_product_links import PackageSize, name_similarity


@pytest.mark.parametrize(
    "value,kind,expected",
    [
        # a UPC-A and the EAN-13 a scanner may read off the same package are the same code
        ("078742351865", None, "0078742351865"),
        ("0078742351865", "EAN-13", "0078742351865"),
        ("0 78742 35186 5", None, "0078742351865"),
        ("5000112637922", "EAN-13", "5000112637922"),
        ("96385074", "EAN-8", "96385074"),
        # a UPC-E is its UPC-A with zeros left out
        ("04252614", "UPC-E", "0042100005264"),
        ("04252614", None, "0042100005264"),
        ("00078742351865", None, "0078742351865"),
        ("078742351866", None, None),
        ("12345", None, None),
        ("", None, None),
        ("not a barcode", None, None),
    ],
)
def test_barcodes_are_checked_and_kept_as_13_digits(value: str, kind: str | None, expected: str | None):
    assert normalize_barcode(value, kind) == expected


@pytest.mark.parametrize(
    "upce,upca",
    [
        ("04252614", "042100005264"),  # sixth digit 0-2: the manufacturer code keeps it
        ("01234565", "012345000065"),  # 5-9: the item number is that digit
        ("01234533", "012300000453"),  # 3
        ("01234547", "012340000057"),  # 4
    ],
)
def test_upce_expands_by_its_sixth_digit(upce: str, upca: str):
    assert expand_upce(upce) == upca


@pytest.mark.parametrize(
    "brands,store",
    [
        ("Great Value", GroceryStore.walmart),
        ("Marketside, Walmart", GroceryStore.walmart),
        ("Friendly Farms", GroceryStore.aldi),
        ("Clancy’s", GroceryStore.aldi),
        ("365 by Whole Foods Market", GroceryStore.whole_foods),
        ("Cub Foods", GroceryStore.cub),
        ("Essential Everyday", GroceryStore.cub),
        ("Kemps", None),
        ("Cubes Inc", None),
        ("", None),
        (None, None),
    ],
)
def test_store_brands_name_their_store(brands: str | None, store: GroceryStore | None):
    assert store_for_brand(brands) == store


GREAT_VALUE_MILK = {
    "code": "0078742351865",
    "status": 1,
    "product": {
        "brands": "Great Value",
        "categories_tags": ["en:dairies", "en:milks", "en:whole-milks"],
        "product_name": "Whole Milk",
        "product_name_en": "Whole Milk",
        "product_quantity": 3785.41,
        "product_quantity_unit": "ml",
        "quantity": "1 gallon",
    },
}


def test_an_open_food_facts_listing_is_read():
    product = parse_food_facts("0078742351865", GREAT_VALUE_MILK)

    assert product == PackagedProduct(
        barcode="0078742351865",
        name="Whole Milk",
        brand="Great Value",
        quantity="1 gallon",
        categories=["dairies", "milks", "whole milks"],
        size=PackageSize(128, GroceryUnit.fluid_ounce),
    )
    assert product.listing == "Great Value Whole Milk 1 gallon"


def test_a_listing_without_a_printed_size_uses_its_measured_one():
    data = {"status": 1, "product": {"product_name": "Penne", "product_quantity": 454, "product_quantity_unit": "g"}}
    product = parse_food_facts("0076808280739", data)
    assert product is not None
    assert product.size == PackageSize(454, GroceryUnit.gram)


@pytest.mark.parametrize(
    "data",
    [
        {"status": 0, "status_verbose": "product not found"},
        {"status": 1, "product": {"brands": "Kemps"}},
        {"status": 1, "product": None},
    ],
)
def test_listings_without_a_product_name_are_unknown(data: dict):
    assert parse_food_facts("0041483022011", data) is None


@pytest.mark.parametrize(
    "first,second,alike",
    [
        ("Great Value Whole Milk, 1 gal", "Great Value Whole Vitamin D Milk Gallon 128 fl oz", True),
        ("Kemps Whole Milk", "Great Value Whole Milk, 1 gal", False),
        ("Barilla Penne, 16 oz", "Barilla Penne Pasta 1 lb", True),
        ("", "Barilla Penne", False),
    ],
)
def test_product_names_are_compared_without_their_sizes(first: str, second: str, alike: bool):
    assert (name_similarity(first, second) >= 0.5) is alike
