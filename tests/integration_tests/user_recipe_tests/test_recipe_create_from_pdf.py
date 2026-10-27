import hashlib
import re
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from slugify import slugify

from mealie.core import exceptions
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.openai.pdf_recipes import OpenAIPdfRecipeLocation, OpenAIPdfRecipeLocations
from mealie.schema.openai.recipe import OpenAIRecipe, OpenAIRecipeIngredient, OpenAIRecipeInstruction
from mealie.schema.reports.reports import ReportCategory, ReportCreate, ReportEntryCreate
from mealie.services.openai import OpenAIService
from mealie.services.recipe.pdf_import import close_interrupted_imports, pdf_import_service
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser
from tests.utils.pdf_builder import PdfImageSpec, PdfPageSpec, build_pdf

RE_PAGE = re.compile(r"--- Page (\d+) ---\n(.*?)(?=\n\n--- Page |\Z)", re.DOTALL)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_import_service, "RETRY_DELAY_SECONDS", 0)


@pytest.fixture(autouse=True)
def ai_providers(unique_user: TestUser) -> Generator[None]:
    provider = unique_user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="gpt-4o", api_key="test-key")
    )
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=provider.id, audio_provider_id=None, image_provider_id=provider.id
        ),
    )

    yield

    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=None, audio_provider_id=None, image_provider_id=None),
    )


class FakeCookbookAI:
    """Stands in for the AI provider. It finds a recipe on every page with an INGREDIENTS heading."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        """The response schema and number of attachments of every request"""

        self.empty_recipes: set[str] = set()
        self.flaky: dict[str, int] = {}
        """Recipes whose requests fail, and how many times before they work"""

        self.usage_limit_on: str | None = None
        self.find_failures = 0
        """How many requests to find the recipes fail before they work"""
        self.organizers: OpenAIOrganizers | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeCookbookAI:
        fake = self

        async def get_response(self, prompt, message, *, response_schema, attachments=None, provider=None):
            fake.calls.append((response_schema.__name__, len(attachments or [])))
            if response_schema is OpenAIPdfRecipeLocations:
                if fake.find_failures:
                    fake.find_failures -= 1
                    raise Exception("OpenAI Request Failed. ChatGPTError: Codex couldn't account/read")
                return fake.find(message)
            if response_schema is OpenAIRecipe:
                return fake.build(message)
            if response_schema is OpenAIOrganizers:
                return fake.organizers
            return None

        monkeypatch.setattr(OpenAIService, "get_response", get_response)
        return self

    def requests_for(self, schema: type) -> list[int]:
        return [attachments for name, attachments in self.calls if name == schema.__name__]

    @staticmethod
    def find(message: str) -> OpenAIPdfRecipeLocations:
        recipes = []
        for number, text in RE_PAGE.findall(message):
            lines = text.splitlines()
            if "INGREDIENTS" in lines:
                page = int(number)
                recipes.append(OpenAIPdfRecipeLocation(name=lines[0].title(), first_page=page, last_page=page))
        return OpenAIPdfRecipeLocations(recipes=recipes)

    def build(self, message: str) -> OpenAIRecipe:
        name = message.splitlines()[0].removeprefix("Recipe: ")
        if name == self.usage_limit_on:
            raise exceptions.RateLimitError("You've hit your usage limit")
        if self.flaky.get(name):
            self.flaky[name] -= 1
            raise Exception("OpenAI Request Failed. ChatGPTError: ChatGPT didn't finish within 300 seconds")
        if name in self.empty_recipes:
            return OpenAIRecipe(name=name)

        return OpenAIRecipe(
            name=name,
            ingredients=[OpenAIRecipeIngredient(text="2 eggs")],
            instructions=[OpenAIRecipeInstruction(text="Cook them.")],
        )


class Cookbook:
    """A small cookbook PDF: a cover, a table of contents, and three recipes, two with photos."""

    def __init__(self, path: Path) -> None:
        self.recipes = [random_string() for _ in range(3)]
        pancakes, waffles, omelette = self.recipes
        photo = PdfImageSpec(left=300, bottom=300, width=250, height=300)

        self.path = build_pdf(
            path,
            [
                PdfPageSpec(lines=["BREAKFAST BOOK"]),
                PdfPageSpec(lines=["CONTENTS", *(f"{name} 3" for name in self.recipes)]),
                PdfPageSpec(lines=[pancakes.upper(), "INGREDIENTS", "2 eggs", "INSTRUCTIONS"], images=[photo]),
                PdfPageSpec(lines=[waffles.upper(), "INGREDIENTS", "2 eggs", "INSTRUCTIONS"], images=[photo]),
                PdfPageSpec(lines=[omelette.upper(), "INGREDIENTS", "2 eggs", "INSTRUCTIONS"]),
            ],
        )

    @property
    def names(self) -> list[str]:
        return [name.title() for name in self.recipes]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


@pytest.fixture()
def cookbook(tmp_path: Path) -> Cookbook:
    return Cookbook(tmp_path.joinpath("breakfast.pdf"))


def import_pdf(api_client: TestClient, user: TestUser, pdf: Path, **data: str):
    with pdf.open("rb") as f:
        return api_client.post(
            api_routes.recipes_create_pdf,
            data=data,
            files=[("file", (pdf.name, f, "application/pdf"))],
            headers=user.token,
        )


def get_report(api_client: TestClient, user: TestUser, report_id: str) -> dict:
    r = api_client.get(api_routes.groups_reports_item_id(report_id), headers=user.token)
    assert r.status_code == 200
    return r.json()


def get_recipe(api_client: TestClient, user: TestUser, name: str) -> dict:
    r = api_client.get(api_routes.recipes_slug(slugify(name)), headers=user.token)
    assert r.status_code == 200
    return r.json()


def test_import_pdf_creates_every_recipe(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    book_name = random_string()

    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    assert r.status_code == 202

    # the import runs in the background, but the test client waits for it
    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["name"] == book_name
    assert report["category"] == "pdf_import"
    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]] == [
        "Recipes found in the PDF: 3, across 5 pages",
        *(f"Imported {name} (page {page})" for name, page in zip(cookbook.names, [3, 4, 5], strict=True)),
    ]

    # one request to find the recipes, then one per recipe with an image of its page
    assert ai.requests_for(OpenAIPdfRecipeLocations) == [0]
    assert ai.requests_for(OpenAIRecipe) == [1, 1, 1]

    for name, page in zip(cookbook.names, [3, 4, 5], strict=True):
        recipe = get_recipe(api_client, unique_user, name)
        assert [tag["name"] for tag in recipe["tags"]] == [book_name]
        source_note = recipe["notes"][-1]
        assert (source_note["title"], source_note["text"]) == ("Source", f"{book_name}, page {page}")
        assert recipe["extras"] == {"pdf_source": f"{cookbook.fingerprint}#page={page}"}

    # the recipes with photos get them, and the image key that tells the frontend to load them
    pancakes = get_recipe(api_client, unique_user, cookbook.names[0])
    assert pancakes["image"]
    r = api_client.get(
        api_routes.media_recipes_recipe_id_images_file_name(pancakes["id"], "original.webp"),
        headers=unique_user.token,
    )
    assert r.status_code == 200
    assert not get_recipe(api_client, unique_user, cookbook.names[2])["image"]

    # and the cookbook shows up under Cookbooks, showing the recipes with its tag
    tag_id = pancakes["tags"][0]["id"]
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    [added] = [cookbook for cookbook in cookbooks if cookbook["name"] == book_name]
    assert added["queryFilterString"] == f'tags.id IN ["{tag_id}"]'


def test_import_pdf_again_skips_the_recipes_already_imported(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    book_name = random_string()
    assert import_pdf(api_client, unique_user, cookbook.path, name=book_name).status_code == 202
    ai.calls.clear()

    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    assert r.status_code == 202

    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]] == [
        "Recipes found in the PDF: 3, across 5 pages",
        "Already imported from this PDF, so skipped: 3",
    ]
    assert ai.requests_for(OpenAIRecipe) == []

    # nothing was imported twice, and there's still just the one cookbook
    r = api_client.get(api_routes.recipes_slug(f"{slugify(cookbook.names[0])}-1"), headers=unique_user.token)
    assert r.status_code == 404
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert [cookbook["name"] for cookbook in cookbooks].count(book_name) == 1


def test_import_pdf_stops_at_the_usage_limit_and_picks_up_where_it_left_off(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.usage_limit_on = cookbook.names[1]

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "partial"
    messages = [entry["message"] for entry in report["entries"]]
    assert messages[1] == f"Imported {cookbook.names[0]} (page 3)"
    assert messages[2].startswith("Stopped because the AI provider's usage limit was reached")
    assert len(messages) == 3
    assert report["entries"][2]["exception"] == "You've hit your usage limit"

    ai.usage_limit_on = None
    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]][1:] == [
        "Already imported from this PDF, so skipped: 1",
        f"Imported {cookbook.names[1]} (page 4)",
        f"Imported {cookbook.names[2]} (page 5)",
    ]


def test_import_pdf_reports_recipes_it_cant_read(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.empty_recipes = {cookbook.names[1]}

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "partial"
    failed = [entry for entry in report["entries"] if not entry["success"]]
    assert [entry["message"] for entry in failed] == [f"Couldn't import {cookbook.names[1]} (page 4)"]
    assert get_recipe(api_client, unique_user, cookbook.names[2])
    # the AI found no recipe there, which asking again wouldn't change
    assert len(ai.requests_for(OpenAIRecipe)) == 3


def test_import_pdf_tries_a_failed_recipe_again_at_the_end(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.flaky = {cookbook.names[0]: 1}

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]][1:] == [
        f"Imported {cookbook.names[1]} (page 4)",
        f"Imported {cookbook.names[2]} (page 5)",
        f"Imported {cookbook.names[0]} (page 3)",
    ]
    assert len(ai.requests_for(OpenAIRecipe)) == 4


def test_import_pdf_tries_finding_recipes_again(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.find_failures = 1

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert len(ai.requests_for(OpenAIPdfRecipeLocations)) == 2
    assert len(ai.requests_for(OpenAIRecipe)) == 3


def test_import_pdf_reports_pages_it_cant_look_through(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.find_failures = 2

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "failure"
    assert [entry["message"] for entry in report["entries"]] == [
        "Couldn't look for recipes on pages 1 to 5",
        "No recipes were found in the PDF",
    ]


def test_import_pdf_reports_a_recipe_that_fails_twice(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.flaky = {cookbook.names[0]: 2}

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "partial"
    failed = [entry for entry in report["entries"] if not entry["success"]]
    assert [entry["message"] for entry in failed] == [f"Couldn't import {cookbook.names[0]} (page 3)"]
    assert "didn't finish within 300 seconds" in failed[0]["exception"]


def test_import_pdf_with_no_recipes_fails(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    FakeCookbookAI().install(monkeypatch)
    pdf = build_pdf(tmp_path.joinpath("novel.pdf"), [PdfPageSpec(lines=["CHAPTER ONE", random_string()])])

    r = import_pdf(api_client, unique_user, pdf)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "failure"
    assert [entry["message"] for entry in report["entries"]] == ["No recipes were found in the PDF"]
    # without a name, the import is named after the file
    assert report["name"] == "novel"


def test_import_pdf_without_an_image_provider_sends_only_text(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    settings = unique_user.repos.group_ai_provider_settings.get_one(unique_user.repos.group_id)
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=settings.default_provider_id, audio_provider_id=None, image_provider_id=None
        ),
    )

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())

    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
    assert ai.requests_for(OpenAIRecipe) == [0, 0, 0]
    # the photos come from the PDF itself, so they're still imported
    assert get_recipe(api_client, unique_user, cookbook.names[0])["image"]


def test_import_pdf_can_add_organizers(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    breakfast = random_string()
    ai.organizers = OpenAIOrganizers(tags=[breakfast], categories=[], tools=[])
    book_name = random_string()

    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name, addOrganizers="true", addCookbook="false")

    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
    assert len(ai.requests_for(OpenAIOrganizers)) == 3
    recipe = get_recipe(api_client, unique_user, cookbook.names[0])
    assert sorted(tag["name"] for tag in recipe["tags"]) == sorted([breakfast, book_name])

    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert book_name not in [cookbook["name"] for cookbook in cookbooks]


def test_import_pdf_rejects_files_that_arent_pdfs(api_client: TestClient, unique_user: TestUser, tmp_path: Path):
    not_a_pdf = tmp_path.joinpath("recipes.pdf")
    not_a_pdf.write_text("Pancakes: 2 eggs, cook them.")

    r = import_pdf(api_client, unique_user, not_a_pdf)

    assert r.status_code == 400
    assert r.json()["detail"]["message"].startswith("That file isn't a PDF Mealie can read")


def test_import_pdf_needs_ai(api_client: TestClient, unique_user: TestUser, cookbook: Cookbook):
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=None, audio_provider_id=None, image_provider_id=None),
    )

    r = import_pdf(api_client, unique_user, cookbook.path)

    assert r.status_code == 400
    assert r.json()["detail"]["message"] == "AI services are not enabled"


def test_import_pdf_rejects_a_pdf_that_is_already_being_imported(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    monkeypatch.setattr(pdf_import_service, "_running_imports", {(unique_user.repos.group_id, cookbook.fingerprint)})

    r = import_pdf(api_client, unique_user, cookbook.path)

    assert r.status_code == 409


def test_pdf_imports_are_listed_with_their_reports(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    FakeCookbookAI().install(monkeypatch)
    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())
    report_id = r.json()["reportId"]

    r = api_client.get(api_routes.groups_reports, params={"report_type": "pdf_import"}, headers=unique_user.token)

    assert r.status_code == 200
    assert report_id in [report["id"] for report in r.json()]


def test_imports_interrupted_by_a_restart_are_closed_on_startup(api_client: TestClient, unique_user: TestUser):
    def running_import(*entries: bool) -> str:
        report = unique_user.repos.group_reports.create(
            ReportCreate(name=random_string(), category=ReportCategory.pdf_import, group_id=unique_user.group_id)
        )
        for success in entries:
            unique_user.repos.group_report_entries.create(
                ReportEntryCreate(report_id=report.id, success=success, message=random_string())
            )
        return str(report.id)

    partway = running_import(True, True)
    before_any_recipe = running_import()

    close_interrupted_imports()

    report = get_report(api_client, unique_user, partway)
    assert report["status"] == "partial"
    assert any(
        entry["message"].startswith("Mealie restarted before this import finished") for entry in report["entries"]
    )
    assert get_report(api_client, unique_user, before_any_recipe)["status"] == "failure"
