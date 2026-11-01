import json

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from tests.utils import api_routes, random_string
from tests.utils.fixture_schemas import TestUser

FIND_BY_SOURCE = "/api/recipes/find-by-source"


def parse_sse_events(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        event: dict = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event["event"] = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                event["data"] = json.loads(line.removeprefix("data:").strip())
        if event:
            events.append(event)
    return events


def save_recipe_from(api_client: TestClient, user: TestUser, url: str) -> dict:
    name = random_string(12)
    response = api_client.post(api_routes.recipes, json={"name": name}, headers=user.token)
    assert response.status_code == 201
    slug = response.json()
    response = api_client.patch(api_routes.recipes_slug(slug), json={"orgURL": url}, headers=user.token)
    assert response.status_code == 200
    return response.json()


def test_find_by_source_matches_however_the_link_was_shared(api_client: TestClient, unique_user: TestUser):
    post = random_string(11)
    page = random_string(10)
    recipe = save_recipe_from(api_client, unique_user, f"https://www.instagram.com/p/{post}/")
    page_recipe = save_recipe_from(api_client, unique_user, f"https://example.test/{page}/")

    urls = [
        f"https://instagram.com/reel/{post}?igsh=shared",
        f"http://example.test/{page}?utm_source=newsletter",
        f"https://example.test/{page}-verde",
        "https://example.test/nothing-like-it",
    ]
    response = api_client.post(FIND_BY_SOURCE, json={"urls": urls}, headers=unique_user.token)

    assert response.status_code == 200
    matches = response.json()
    assert [(m["url"], m["slug"]) for m in matches] == [
        (urls[0], recipe["slug"]),
        (urls[1], page_recipe["slug"]),
    ]
    assert matches[0]["name"] == recipe["name"]


def test_find_by_source_includes_other_households_in_the_group(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser
):
    url = f"https://example.test/{random_string(12)}"
    recipe = save_recipe_from(api_client, h2_user, url)

    response = api_client.post(FIND_BY_SOURCE, json={"urls": [url]}, headers=unique_user.token)

    assert [m["slug"] for m in response.json()] == [recipe["slug"]]


def test_find_by_source_stays_within_the_group(api_client: TestClient, unique_user: TestUser, g2_user: TestUser):
    url = f"https://example.test/{random_string(12)}"
    save_recipe_from(api_client, g2_user, url)

    response = api_client.post(FIND_BY_SOURCE, json={"urls": [url]}, headers=unique_user.token)

    assert response.json() == []


def test_import_refuses_a_link_already_saved(api_client: TestClient, unique_user: TestUser, monkeypatch: MonkeyPatch):
    url = f"https://example.test/{random_string(12)}"
    recipe = save_recipe_from(api_client, unique_user, url)

    async def must_not_scrape(*args, **kwargs):
        raise AssertionError("a saved link should be refused before scraping")

    monkeypatch.setattr("mealie.routes.recipe.recipe_crud_routes.create_from_html", must_not_scrape)

    response = api_client.post(
        api_routes.recipes_create_url, json={"url": f"{url}/?utm_source=share"}, headers=unique_user.token
    )

    assert response.status_code == 400
    assert recipe["name"] in response.json()["detail"]["message"]


def test_import_again_when_asked(api_client: TestClient, unique_user: TestUser, monkeypatch: MonkeyPatch):
    url = f"https://example.test/{random_string(12)}"
    save_recipe_from(api_client, unique_user, url)
    scraped: list[str] = []

    async def record_scrape(url: str, *args, **kwargs):
        scraped.append(url)
        raise Exception("stop after the duplicate check")

    monkeypatch.setattr("mealie.routes.recipe.recipe_crud_routes.create_from_html", record_scrape)

    response = api_client.post(
        api_routes.recipes_create_url_stream,
        json={"url": url, "allowDuplicate": True},
        headers=unique_user.token,
    )

    assert response.status_code == 200
    assert scraped == [url]


def test_bulk_import_skips_saved_and_repeated_links(
    api_client: TestClient, unique_user: TestUser, monkeypatch: MonkeyPatch
):
    saved_url = f"https://example.test/{random_string(12)}"
    recipe = save_recipe_from(api_client, unique_user, saved_url)
    new_url = f"https://example.test/{random_string(12)}"
    scraped: list[str] = []

    async def record_scrape(url: str, *args, **kwargs):
        scraped.append(url)
        raise Exception("not a real page")

    monkeypatch.setattr("mealie.services.scraper.recipe_bulk_scraper.create_from_html", record_scrape)

    response = api_client.post(
        api_routes.recipes_create_url_bulk,
        json={"imports": [{"url": f"{saved_url}?fbclid=1"}, {"url": new_url}, {"url": f"{new_url}/"}]},
        headers=unique_user.token,
    )
    assert response.status_code == 202

    report = api_client.get(
        api_routes.groups_reports_item_id(response.json()["reportId"]), headers=unique_user.token
    ).json()
    messages = [entry["message"] for entry in report["entries"]]

    assert scraped == [new_url]
    assert any(recipe["name"] in message for message in messages)
    assert any("listed twice" in message for message in messages)
