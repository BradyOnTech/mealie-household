"""
Finds the written recipe a video's description links to.

Cooking channels often publish a written version of a video's recipe on their own site, and link to
it from the description. It has exact amounts where the video might only say "a splash", so it's
read alongside the video's transcript.
"""

import asyncio
import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from mealie.core.root_logger import get_logger
from mealie.pkgs.safehttp import resilient_fetch
from mealie.services.openai.content import find_json_ld_recipes
from mealie.services.scraper import cleaner

logger = get_logger()

MAX_LINKS = 3
"""Most links read from one description, so a description full of links can't drag an import out"""

LINK_TIMEOUT = 20
"""Seconds to spend reading each link. The links are read at the same time."""

RECIPE_WORDS = ("recipe", "receta", "recette", "rezept", "ricetta", "receita", "recept")
"""Words that introduce a link to a written recipe, in the languages cooking channels use most"""

SKIPPED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "threads.net",
    "pinterest.com",
    "patreon.com",
    "amzn.to",
)
"""Sites that never publish a written recipe, though descriptions often mention recipes beside them"""

FILLER_WORDS = frozenset(
    "a an and or the of with in on for to at by from my our your how make making made recipe recipes "
    "easy best ever homemade simple quick ultimate perfect video".split()
)
"""Words that say nothing about which recipe a name is for"""

URL_PATTERN = re.compile(r"https?://[^\s<>\"'()\[\]{}]+")
WORD_PATTERN = re.compile(r"[^\W_]+")

RECIPE_FIELDS = (
    "name",
    "description",
    "recipeYield",
    "prepTime",
    "cookTime",
    "totalTime",
    "recipeIngredient",
    "recipeInstructions",
    "nutrition",
)
"""The parts of a recipe's structured data that describe the recipe itself"""

INSTRUCTION_FIELDS = ("@type", "name", "text", "itemListElement")


@dataclass
class LinkedRecipe:
    url: str
    """Where the recipe was read from, after any redirects"""

    data: dict[str, Any]
    """The recipe's schema.org data"""

    @property
    def content(self) -> str:
        fields = {key: self.data[key] for key in RECIPE_FIELDS if self.data.get(key)}
        if "recipeInstructions" in fields:
            fields["recipeInstructions"] = _trim_instructions(fields["recipeInstructions"])

        return json.dumps(_unescape(fields), ensure_ascii=False, indent=2)

    @property
    def image_url(self) -> str | None:
        return cleaner.clean_image(self.data.get("image"), default="")[0] or None


def recipe_links(description: str) -> list[str]:
    """
    Links in a video's description that are introduced as a recipe, like "Full recipe: <link>",
    or a link on the line after "RECIPE 👇".
    """

    links: list[str] = []
    previous_line = ""
    for line in description.splitlines():
        context = f"{previous_line} {line}".casefold()
        if line.strip():
            previous_line = line

        if not any(word in context for word in RECIPE_WORDS):
            continue

        for url in URL_PATTERN.findall(line):
            url = url.rstrip(".,;:!?")
            if url not in links and not _is_skipped(url):
                links.append(url)

    return links[:MAX_LINKS]


def _is_skipped(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold()
    return "amazon" in host.split(".") or any(
        host == skipped or host.endswith(f".{skipped}") for skipped in SKIPPED_HOSTS
    )


def _name_words(text: str) -> set[str]:
    words = (word for word in WORD_PATTERN.findall(text.casefold()) if word not in FILLER_WORDS)
    # fold simple plurals, so that "cookies" matches "cookie"
    return {word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words}


def names_match(recipe_name: str, video_title: str) -> bool:
    """
    Whether most of a recipe's name is words from the video's title. Titles carry plenty besides
    the dish ("I Tried the Viral Feta Pasta (It's Amazing)"), but a recipe's name rarely does, so
    it's measured against the name. Half isn't enough: a pizza video's "Pizza Sauce" isn't its pizza.
    """

    recipe_words = _name_words(recipe_name)
    if not recipe_words:
        return False

    return len(recipe_words & _name_words(video_title)) * 2 > len(recipe_words)


async def find_linked_recipe(video_title: str, links: list[str]) -> LinkedRecipe | None:
    """
    Reads the links, and returns the first recipe among them whose name matches the video's title.
    Descriptions link to other recipes too ("my pizza sauce", "more pasta recipes"), and those
    would only muddle the video's own.
    """

    async def read(link: str) -> tuple[str, list[dict[str, Any]]]:
        result = await resilient_fetch(link)
        if not result:
            return link, []

        return result.url, await asyncio.to_thread(find_json_ld_recipes, result.text)

    pages = await asyncio.gather(
        *(asyncio.wait_for(read(link), LINK_TIMEOUT) for link in links),
        return_exceptions=True,
    )

    for link, page in zip(links, pages, strict=True):
        if isinstance(page, BaseException):
            logger.info(f"Couldn't read the recipe linked from a video at {link}: {page!r}")
            continue

        url, recipes = page
        for recipe in recipes:
            if names_match(str(recipe.get("name") or ""), video_title):
                return LinkedRecipe(url=url, data=recipe)

    return None


def _trim_instructions(value: Any) -> Any:
    """
    Drops each step's URL, image, and the like, which say nothing about how to cook it, and the
    name many sites give a step by copying its text.
    """

    if isinstance(value, list):
        return [_trim_instructions(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _trim_instructions(item)
            for key, item in value.items()
            if key in INSTRUCTION_FIELDS and not (key == "name" and item == value.get("text"))
        }

    return value


def _unescape(value: Any) -> Any:
    """Decodes HTML entities, which sites often leave in their structured data"""

    if isinstance(value, str):
        return html.unescape(value)
    if isinstance(value, list):
        return [_unescape(item) for item in value]
    if isinstance(value, dict):
        return {key: _unescape(item) for key, item in value.items()}

    return value
