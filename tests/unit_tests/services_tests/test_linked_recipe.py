import asyncio
import json
from typing import Any

import httpx
import pytest

import mealie.services.recipe.import_workflow.compilers.linked_recipe as linked_recipe_module
from mealie.pkgs.safehttp.fetch import FetchResult
from mealie.services.openai.content import find_json_ld_recipes, has_recipe_data
from mealie.services.recipe.import_workflow.compilers.linked_recipe import (
    LinkedRecipe,
    find_linked_recipe,
    names_match,
    recipe_links,
)


def _page(*blocks: Any) -> str:
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(block)}</script>' for block in blocks)
    return f"<html><head>{scripts}</head><body>A recipe</body></html>"


def test_recipe_links_are_found_by_what_introduces_them():
    description = "\n".join(
        [
            "For more cooking science, get my book: https://www.example.com/book",
            "Here's the full recipe and a bit of science: https://www.seriouseats.com/pan-pizza.",
            "",
            "WRITTEN RECIPE 👇",
            "",
            "https://kenji.test/pizza",
            "Merch: https://shop.test/hoodie",
        ]
    )

    assert recipe_links(description) == ["https://www.seriouseats.com/pan-pizza", "https://kenji.test/pizza"]


def test_recipe_links_skip_social_and_shopping_sites():
    description = "\n".join(
        [
            "Recipe video on TikTok: https://www.tiktok.com/@chef/video/123",
            "More recipes on Instagram: https://instagram.com/chef",
            "My recipe book: https://amzn.to/abc and https://www.amazon.co.uk/dp/123",
            "The recipe I riffed on: https://youtu.be/abc",
            "Recette : https://cuisine.test/tarte",
        ]
    )

    assert recipe_links(description) == ["https://cuisine.test/tarte"]


def test_recipe_links_are_capped():
    description = "\n".join(f"Recipe {n}: https://recipes.test/{n}" for n in range(10))

    assert recipe_links(description) == [f"https://recipes.test/{n}" for n in range(linked_recipe_module.MAX_LINKS)]


def test_recipe_links_in_a_description_without_any():
    assert recipe_links("") == []
    assert recipe_links("Subscribe! https://youtube.com/@chef\nMy knives: https://knives.test") == []


@pytest.mark.parametrize(
    ("recipe_name", "video_title", "expected"),
    [
        ("Foolproof Pan Pizza Recipe", "Food Lab Basics: POV Foolproof No Knead Pan Pizza", True),
        ("Chocolate Chip Cookies", "The BEST Chewy Chocolate Chip Cookie | Babish", True),
        ("Baked Feta Pasta", "I Tried the Viral Feta Pasta (It's Amazing)", True),
        ("Crème Brûlée", "Crème brûlée, the easy way", True),
        ("New York-Style Pizza Sauce", "Foolproof Pan Pizza", False),
        ("Pizza Sauce", "Foolproof Pan Pizza", False),
        ("Crispy Chicken Thighs with Roasted Sweet Potatoes", "Three Chicken Techniques Every Cook Should Know", False),
        ("The Best Recipe", "The Best Recipe Ever", False),
        ("", "Foolproof Pan Pizza", False),
    ],
)
def test_names_match(recipe_name: str, video_title: str, expected: bool):
    assert names_match(recipe_name, video_title) is expected


@pytest.fixture()
def pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What each URL serves: a page, a (page, landing URL) pair, None, or an exception to raise"""

    served: dict[str, Any] = {}

    async def mock_resilient_fetch(url: str) -> FetchResult | None:
        page = served.get(url)
        if isinstance(page, BaseException):
            raise page
        if page is None:
            return None

        html, landing_url = page if isinstance(page, tuple) else (page, url)
        return FetchResult(html.encode(), 200, landing_url, httpx.Headers(), "utf-8")

    monkeypatch.setattr(linked_recipe_module, "resilient_fetch", mock_resilient_fetch)
    return served


@pytest.mark.asyncio
async def test_the_linked_recipe_matching_the_video_is_found(pages: dict[str, Any]):
    pages["https://sauce.test"] = _page({"@type": "Recipe", "name": "Pizza Sauce"})
    pages["http://pizza.test"] = (
        _page({"@graph": [{"@type": "WebPage"}, {"@type": "Recipe", "name": "Pan Pizza"}]}),
        "https://pizza.test/pan-pizza",
    )

    linked = await find_linked_recipe("Foolproof Pan Pizza", ["https://sauce.test", "http://pizza.test"])

    assert linked is not None
    assert linked.url == "https://pizza.test/pan-pizza"
    assert linked.data["name"] == "Pan Pizza"


@pytest.mark.asyncio
async def test_no_linked_recipe_when_none_match(pages: dict[str, Any]):
    pages["https://sauce.test"] = _page({"@type": "Recipe", "name": "Pizza Sauce"})
    pages["https://book.test"] = "<html><body>Buy my book</body></html>"

    assert await find_linked_recipe("Foolproof Pan Pizza", ["https://sauce.test", "https://book.test"]) is None


@pytest.mark.asyncio
async def test_links_that_fail_are_skipped(pages: dict[str, Any]):
    pages["https://dead.test"] = RuntimeError("could not resolve host: dead.test")
    pages["https://gone.test"] = None
    pages["https://pizza.test"] = _page({"@type": "Recipe", "name": "Pan Pizza"})

    linked = await find_linked_recipe("Pan Pizza", ["https://dead.test", "https://gone.test", "https://pizza.test"])

    assert linked is not None
    assert linked.url == "https://pizza.test"


@pytest.mark.asyncio
async def test_links_that_take_too_long_are_skipped(monkeypatch: pytest.MonkeyPatch):
    async def slow_fetch(url: str) -> FetchResult:
        await asyncio.sleep(10)
        raise AssertionError("should have timed out")

    monkeypatch.setattr(linked_recipe_module, "LINK_TIMEOUT", 0.05)
    monkeypatch.setattr(linked_recipe_module, "resilient_fetch", slow_fetch)

    assert await find_linked_recipe("Pan Pizza", ["https://slow.test"]) is None


def test_linked_recipe_content_keeps_only_the_recipe():
    linked = LinkedRecipe(
        url="https://pizza.test",
        data={
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "John&#39;s Pan Pizza",
            "author": {"@type": "Person", "name": "John"},
            "aggregateRating": {"ratingValue": 5},
            "recipeYield": "2 pizzas",
            "recipeIngredient": ["400g flour &amp; salt"],
            "recipeInstructions": [
                {
                    "@type": "HowToSection",
                    "name": "Dough",
                    "itemListElement": [
                        {
                            "@type": "HowToStep",
                            "name": "Mix everything.",
                            "text": "Mix everything.",
                            "url": "https://pizza.test#step-1",
                            "image": "https://pizza.test/step-1.jpg",
                        }
                    ],
                }
            ],
            "image": ["https://pizza.test/pizza.jpg", "https://pizza.test/pizza-square.jpg"],
        },
    )

    assert json.loads(linked.content) == {
        "name": "John's Pan Pizza",
        "recipeYield": "2 pizzas",
        "recipeIngredient": ["400g flour & salt"],
        "recipeInstructions": [
            {
                "@type": "HowToSection",
                "name": "Dough",
                "itemListElement": [{"@type": "HowToStep", "text": "Mix everything."}],
            }
        ],
    }
    assert linked.image_url == "https://pizza.test/pizza.jpg"


def test_linked_recipe_without_an_image():
    assert LinkedRecipe(url="https://pizza.test", data={"name": "Pan Pizza"}).image_url is None


@pytest.mark.parametrize(
    ("blocks", "names"),
    [
        pytest.param([{"@type": "Recipe", "name": "a"}], ["a"], id="top level"),
        pytest.param([[{"@type": "Recipe", "name": "a"}, {"@type": "Recipe", "name": "b"}]], ["a", "b"], id="a list"),
        pytest.param([{"@graph": [{"@type": "Organization"}, {"@type": "Recipe", "name": "a"}]}], ["a"], id="a graph"),
        pytest.param([{"@type": "WebPage", "mainEntity": {"@type": "Recipe", "name": "a"}}], ["a"], id="main entity"),
        pytest.param([{"@type": ["Recipe", "NewsArticle"], "name": "a"}], ["a"], id="several types"),
        pytest.param([{"@type": "http://schema.org/Recipe", "name": "a"}], ["a"], id="a full type URL"),
        pytest.param([{"@type": "VideoObject", "name": "a"}], [], id="a video"),
    ],
)
def test_find_json_ld_recipes(blocks: list[Any], names: list[str]):
    assert [recipe["name"] for recipe in find_json_ld_recipes(_page(*blocks))] == names


def test_find_json_ld_recipes_skips_invalid_json():
    html = '<script type="application/ld+json">{not json</script>' + _page({"@type": "Recipe", "name": "a"})

    assert [recipe["name"] for recipe in find_json_ld_recipes(html)] == ["a"]


def test_has_recipe_data():
    assert has_recipe_data(_page({"@type": "Recipe", "name": "Pan Pizza"}))
    # a video's page has structured data, but not a recipe
    assert not has_recipe_data(_page({"@type": "VideoObject", "name": "Pan Pizza Recipe"}))
    assert not has_recipe_data("<html><body>Pan pizza</body></html>")
