"""
Find recipes that were already imported from a link, however that link was shared.

The same recipe arrives under many addresses: with or without "www.", with a trailing slash, with
tracking parameters from whichever app shared it, and for video posts under several paths
(an Instagram post as /p/ or /reel/, a YouTube video as youtu.be or /watch). `source_key` reduces
each to one key, and `RecipeSourceService` compares saved recipes' sources by that key.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from mealie.repos.repository_recipes import RepositoryRecipes
from mealie.schema.recipe.recipe_source_match import RecipeSourceMatch

# Query parameters that say how a link was shared rather than what it points to
TRACKING_PARAM = re.compile(r"^(utm_.*|fbclid|gclid|igsh|igshid|si|srtk|feature|ref|ref_src|share.*|mc_.*|_.*)$", re.I)

# Anything shorter matches too many saved sources to be a useful first pass
MIN_SEARCH_TERM = 4


def _segment_after(segments: list[str], *names: str) -> str | None:
    for index, segment in enumerate(segments[:-1]):
        if segment.lower() in names:
            return segments[index + 1]
    return None


def source_key(url: str | None) -> str | None:
    """
    One key per recipe source: `site:id` for a video post, otherwise host, path and the
    query parameters that matter. Returns None for anything that isn't a web link.
    """
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None

    host = re.sub(r"^(www|m)\.", "", parts.hostname.lower())
    path = parts.path.rstrip("/")
    segments = [segment for segment in path.split("/") if segment]
    query = parse_qsl(parts.query, keep_blank_values=True)

    site, video_id = "", None
    if host == "youtu.be":
        site, video_id = "youtube", segments[0] if segments else None
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        site, video_id = "youtube", dict(query).get("v") or _segment_after(segments, "shorts", "embed", "live")
    elif host == "instagram.com" or host.endswith(".instagram.com"):
        site, video_id = "instagram", _segment_after(segments, "p", "reel", "reels", "tv")
    elif host == "tiktok.com" or host.endswith(".tiktok.com"):
        site, video_id = "tiktok", _segment_after(segments, "video")
    if video_id:
        return f"{site}:{video_id}"

    kept = sorted((name, value) for name, value in query if not TRACKING_PARAM.match(name))
    search = f"?{urlencode(kept)}" if kept else ""
    return f"{host}{path}{search}"


def source_search_term(key: str) -> str | None:
    """The part of a key to look for in saved sources: a video's id, or a page's host and path"""
    if re.match(r"^[a-z]+:", key) and "/" not in key:
        term = key.split(":", 1)[1]
    else:
        term = key.split("?", 1)[0]
    return term if len(term) >= MIN_SEARCH_TERM else None


class DuplicateRecipeSourceError(Exception):
    """A link was imported before. Raised with an already-translated message naming the recipe."""

    def __init__(self, message: str, match: RecipeSourceMatch) -> None:
        super().__init__(message)
        self.match = match


class RecipeSourceService:
    """Looks up saved recipes by where they were imported from"""

    def __init__(self, recipes: RepositoryRecipes) -> None:
        self.recipes = recipes

    def find(self, url: str) -> RecipeSourceMatch | None:
        """The earliest saved recipe imported from the same place as `url`, if any"""
        key = source_key(url)
        term = source_search_term(key) if key else None
        if not key or not term:
            return None

        # The search is loose (it finds /chili-verde for /chili), so each hit is confirmed by key
        for recipe in self.recipes.find_by_source_term(term):
            if source_key(recipe.org_url) == key:
                return RecipeSourceMatch(
                    url=url,
                    id=recipe.id,
                    slug=recipe.slug,
                    name=recipe.name,
                    created_at=recipe.created_at,
                )
        return None

    def find_many(self, urls: list[str]) -> list[RecipeSourceMatch]:
        return [match for url in urls if (match := self.find(url))]
