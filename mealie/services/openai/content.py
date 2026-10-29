import json
from typing import Any

import bs4

MAX_SOURCE_CONTENT_LENGTH = 100_000
"""
Upper bound on how much source text is sent to an AI provider.

Webpages and pasted content are unbounded, and every character costs tokens, so we cut off
anything beyond a length that comfortably fits even a very long recipe.
"""

TRUNCATION_NOTICE = "\n\n[content truncated]"


def truncate_source_content(content: str, max_length: int = MAX_SOURCE_CONTENT_LENGTH) -> str:
    """Caps source content, marking it so the model knows the text is incomplete."""

    if len(content) <= max_length:
        return content

    return content[:max_length] + TRUNCATION_NOTICE


def truncate_source_parts(parts: list[str], max_length: int = MAX_SOURCE_CONTENT_LENGTH) -> list[str]:
    """
    Caps a group of source texts so that their combined length fits `max_length`.

    Each part is allotted an equal share of the budget, and whatever the shorter parts leave
    unused is handed to the longer ones. Truncating the parts as one string instead would let a
    long webpage swallow the whole budget and drop the text pasted alongside it entirely.
    """

    budgets = [0] * len(parts)
    remaining = max_length

    # shortest first, so that whatever a short part doesn't need is still up for grabs
    for position, index in enumerate(sorted(range(len(parts)), key=lambda index: len(parts[index]))):
        budgets[index] = min(len(parts[index]), remaining // (len(parts) - position))
        remaining -= budgets[index]

    return [truncate_source_content(part, budget) for part, budget in zip(parts, budgets, strict=True)]


def extract_json_ld_data_from_html(soup: bs4.BeautifulSoup) -> str:
    data_parts: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            script_data = script.string
            if script_data:
                data_parts.append(str(script_data))
        except AttributeError:
            pass

    return "\n\n".join(data_parts)


def find_json_ld_recipes(html: str) -> list[dict[str, Any]]:
    """
    Every schema.org Recipe in a page's ld+json data, wherever it's nested: at the top level,
    in a list, in an `@graph`, or as a page's `mainEntity`.
    """

    recipes: list[dict[str, Any]] = []
    for script in bs4.BeautifulSoup(html, "lxml").find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue

        recipes.extend(_json_ld_recipes(data))

    return recipes


def _json_ld_recipes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [recipe for item in data for recipe in _json_ld_recipes(item)]
    if not isinstance(data, dict):
        return []

    types = data.get("@type")
    for type_name in types if isinstance(types, list) else [types]:
        # types can be written out in full, e.g. "http://schema.org/Recipe" or "schema:Recipe"
        if isinstance(type_name, str) and type_name.rsplit("/", 1)[-1].rsplit(":", 1)[-1] == "Recipe":
            return [data]

    return _json_ld_recipes(data.get("@graph")) + _json_ld_recipes(data.get("mainEntity"))


def has_recipe_data(html: str) -> bool:
    """
    Whether a page publishes a recipe as schema.org structured data. Other structured data, like
    the VideoObject on a video's page, doesn't count.
    """

    # most pages that don't can be ruled out without parsing them
    return "recipe" in html.lower() and bool(find_json_ld_recipes(html))


def find_image(soup: bs4.BeautifulSoup) -> str | None:
    # find the open graph image tag
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    # find the largest image on the page
    largest_img = None
    max_size = 0
    for img in soup.find_all("img"):
        width = img.get("width", 0)
        height = img.get("height", 0)
        if not width or not height:
            continue

        try:
            size = int(width) * int(height)
        except ValueError, TypeError:
            size = 1
        if size > max_size:
            max_size = size
            largest_img = img

    if largest_img:
        return largest_img.get("src")

    return None


def extract_page_content(html: str) -> tuple[str, str | None]:
    """
    Strips an HTML document down to its text content, with any ld+json data appended,
    along with the page's primary image, if one can be found.

    Raises if the document contains neither text nor ld+json data.
    """

    soup = bs4.BeautifulSoup(html, "lxml")

    text = soup.get_text(separator="\n", strip=True)
    if description := page_description(soup):
        if description not in text:
            text += f"\n\nPage description:\n{description}"
    text += extract_json_ld_data_from_html(soup)
    if not text:
        raise ValueError("No text or ld+json data found in HTML")

    try:
        image = find_image(soup)
    except Exception:
        image = None

    return text, image


def page_description(soup: bs4.BeautifulSoup) -> str:
    """Social posts can publish their whole written recipe only in page metadata."""
    descriptions = [
        str(tag.get("content") or "").strip()
        for tag in soup.select(
            'meta[property="og:description"], meta[name="description"], meta[name="twitter:description"]'
        )
    ]
    return max(descriptions, key=len, default="")
