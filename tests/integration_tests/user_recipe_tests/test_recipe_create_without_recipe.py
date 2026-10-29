"""
A page that has no recipe on it is refused, rather than saved as a bare recipe made from the page's title,
description and photo. The import page then offers other ways in: pasting the recipe's text, or screenshots.
"""

import pytest
from fastapi.testclient import TestClient

import mealie.services.scraper.recipe_scraper as recipe_scraper_module
from mealie.core import exceptions
from mealie.lang import get_locale_provider
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.compiled_source import OpenAICompiledSource
from mealie.services.openai import OpenAIService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

translator = get_locale_provider("en-US")

# A roundup page: plenty to make a recipe's title, description and photo from, but no recipe
PAGE_WITHOUT_RECIPE = """
<html>
  <head>
    <meta property="og:title" content="Our favourite summer dinners">
    <meta property="og:description" content="A roundup of everything we cooked this month">
    <meta property="og:image" content="https://example.com/summer.jpg">
  </head>
  <body><p>Links to every one of them are below.</p></body>
</html>
"""


@pytest.fixture(autouse=True)
def page_without_recipe(monkeypatch: pytest.MonkeyPatch):
    async def get_html(url: str) -> str:
        return PAGE_WITHOUT_RECIPE

    monkeypatch.setattr(recipe_scraper_module, "safe_scrape_html", get_html)


def enable_ai(user: TestUser) -> None:
    provider = user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="test-model", api_key="test-key")
    )
    user.repos.group_ai_provider_settings.update(
        user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=provider.id, audio_provider_id=None, image_provider_id=None),
    )


def import_link(api_client: TestClient, user: TestUser):
    return api_client.post(
        api_routes.recipes_create_url,
        json={"url": f"https://example.com/{random_string()}"},
        headers=user.token,
    )


def test_without_ai_a_page_with_no_recipe_is_refused(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = import_link(api_client, user)

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "BAD_RECIPE_DATA"
    assert user.repos.recipes.get_all() == []


def test_a_page_ai_finds_no_recipe_on_is_refused(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    user = unique_user_fn_scoped
    enable_ai(user)
    asked: list[str] = []

    async def get_response(self, prompt, message, *args, response_schema=None, **kwargs):
        asked.append(response_schema.__name__)
        return OpenAICompiledSource(contains_recipe=False, content="", language=None, image_url=None)

    monkeypatch.setattr(OpenAIService, "get_response", get_response)
    response = import_link(api_client, user)

    assert asked, "the AI should have been asked to read the page"
    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "BAD_RECIPE_DATA"
    assert user.repos.recipes.get_all() == []


def test_an_ai_provider_at_its_limit_says_so(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    """It used to be covered up by a bare recipe; without one, it would read as the page having no recipe."""

    user = unique_user_fn_scoped
    enable_ai(user)

    async def get_response(self, *args, **kwargs):
        raise exceptions.RateLimitError("You've hit your usage limit")

    monkeypatch.setattr(OpenAIService, "get_response", get_response)
    response = import_link(api_client, user)

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == translator.t("exceptions.rate-limit-error")
    assert user.repos.recipes.get_all() == []


def test_bulk_imports_report_a_page_with_no_recipe(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.post(
        api_routes.recipes_create_url_bulk,
        json={"imports": [{"url": "https://example.com/roundup"}]},
        headers=user.token,
    )
    assert response.status_code == 202

    report = user.repos.group_reports.get_one(response.json()["reportId"])
    assert report is not None
    assert report.status == "failure"
    [entry] = report.entries
    assert entry.message == "Couldn't import https://example.com/roundup"
    assert entry.exception == "No recipe was found on that page"
    assert user.repos.recipes.get_all() == []
