from uuid import uuid4

import pytest

from mealie.schema.grocery.grocery import GroceryStore, GroceryUnit
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientFoodAlias
from mealie.services.household_services.grocery_product_links import (
    PackageSize,
    candidate_foods,
    match_food,
    package_size,
    product_text,
    store_for_url,
    tidy_name,
)


@pytest.mark.parametrize(
    "url,store,name",
    [
        (
            "https://www.walmart.com/ip/Great-Value-Whole-Vitamin-D-Milk-Gallon-128-fl-oz/10450114",
            GroceryStore.walmart,
            "Great Value Whole Vitamin D Milk Gallon 128 fl oz",
        ),
        (
            "https://www.walmart.com/ip/Great-Value-Large-White-Eggs-12-Count/145051970?athbdg=L1600",
            GroceryStore.walmart,
            "Great Value Large White Eggs 12 Count",
        ),
        ("https://www.cub.com/store/cub/products/2793610-cub-milk-whole-1-gl", GroceryStore.cub, "Cub Milk Whole 1 gl"),
        (
            "https://cub.com/product/kemps-select-whole-milk-id-00041483022011",
            GroceryStore.cub,
            "Kemps Select Whole Milk",
        ),
        (
            "https://www.aldi.us/store/aldi/products/18647583-friendly-farms-whole-milk-0-5-gal",
            GroceryStore.aldi,
            "Friendly Farms Whole Milk 0.5 gal",
        ),
        (
            "https://www.aldi.us/products/dairy-eggs/milk-milk-substitutes/detail/ps/p/friendly-farms-whole-milk-one-half-gallon/",
            GroceryStore.aldi,
            "Friendly Farms Whole Milk One Half Gallon",
        ),
        (
            "https://www.wholefoodsmarket.com/product/365-by-whole-foods-market-organic-whole-milk-128-fl-oz-b074h56r6v",
            GroceryStore.whole_foods,
            "365 by Whole Foods Market Organic Whole Milk 128 fl oz",
        ),
    ],
)
def test_a_store_link_names_its_product(url: str, store: GroceryStore, name: str):
    assert store_for_url(url) == store
    assert tidy_name(product_text(url)) == name


def test_links_without_a_name_give_none():
    assert product_text("https://www.walmart.com/ip/10450114") == ""
    assert store_for_url("https://example.com/milk") is None


@pytest.mark.parametrize(
    "text,size",
    [
        ("Great Value Whole Vitamin D Milk Gallon 128 fl oz", PackageSize(128, GroceryUnit.fluid_ounce)),
        ("Cub Milk Whole 1 gl", PackageSize(128, GroceryUnit.fluid_ounce)),
        ("Friendly Farms Whole Milk 0.5 gal", PackageSize(64, GroceryUnit.fluid_ounce)),
        ("Friendly Farms Whole Milk One Half Gallon", PackageSize(64, GroceryUnit.fluid_ounce)),
        ("Heavy Whipping Cream 1 qt", PackageSize(32, GroceryUnit.fluid_ounce)),
        ("Barilla Spaghetti 16 oz", PackageSize(16, GroceryUnit.ounce)),
        ("Chicken Breasts 2.5 lb", PackageSize(2.5, GroceryUnit.pound)),
        ("Basmati Rice 2kg", PackageSize(2, GroceryUnit.kilogram)),
        ("Olive Oil 750 ml", PackageSize(750, GroceryUnit.milliliter)),
        ("Large White Eggs 12 Count", PackageSize(12, GroceryUnit.COUNT)),
        ("Free Range Eggs Dozen", PackageSize(12, GroceryUnit.COUNT)),
        ("Sparkling Water 8 pack", PackageSize(8, GroceryUnit.COUNT)),
    ],
)
def test_package_sizes_come_in_the_lists_units(text: str, size: PackageSize):
    assert package_size(text) == size


def test_a_name_without_a_size_has_none():
    assert package_size("Kemps Select Whole Milk") is None
    assert package_size("Great Value 2% Reduced Fat Milk") is None


def food(name: str, plural: str | None = None, aliases: tuple[str, ...] = ()) -> IngredientFood:
    return IngredientFood(
        id=uuid4(), name=name, plural_name=plural, aliases=[IngredientFoodAlias(name=alias) for alias in aliases]
    )


FOODS = [
    food("milk"),
    food("almond milk"),
    food("egg"),
    food("butter"),
    food("peanut butter"),
    food("garlic"),
    food("bread"),
    food("tomato", "tomatoes"),
    food("scallion", aliases=("green onion",)),
]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Great Value Whole Vitamin D Milk Gallon 128 fl oz", "milk"),
        ("Silk Unsweetened Almond Milk 64 fl oz", "almond milk"),
        ("Great Value Large White Eggs 12 Count", "egg"),
        ("Jif Creamy Peanut Butter 16 oz", "peanut butter"),
        ("Pepperidge Farm Garlic Bread", "bread"),
        ("Roma Tomatoes 2 lb", "tomato"),
        ("Fresh Green Onions Bunch", "scallion"),
        ("Dawn Dish Soap", None),
    ],
)
def test_the_most_specific_ingredient_in_the_name_is_chosen(text: str, expected: str | None):
    match = match_food(text, FOODS)
    assert (match.name if match else None) == expected


def test_the_ai_gets_the_ingredients_that_share_a_word():
    names = [candidate.name for candidate in candidate_foods("Silk Unsweetened Almond Milk", FOODS)]
    assert names[0] == "almond milk"
    assert set(names) == {"almond milk", "milk"}
