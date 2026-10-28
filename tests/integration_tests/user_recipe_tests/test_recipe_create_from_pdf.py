import hashlib
import re
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from slugify import slugify

from mealie.core import exceptions
from mealie.repos.repository_cookbooks import RepositoryCookbooks
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate, AITask, AITaskSettingUpdate
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.openai.pdf_recipes import OpenAIPdfRecipeLocation, OpenAIPdfRecipeLocations
from mealie.schema.openai.recipe import OpenAIRecipe, OpenAIRecipeIngredient, OpenAIRecipeInstruction
from mealie.schema.reports.reports import ReportCategory, ReportCreate, ReportEntryCreate
from mealie.services.openai import OpenAIService
from mealie.services.recipe.pdf_import import close_interrupted_imports, epub_document, pdf_import_service
from tests.utils import api_routes
from tests.utils.epub_builder import EpubChapterSpec, EpubImageSpec, build_epub
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
        self.tasks: list[tuple[str, AITask | None]] = []
        """The response schema and AI task of every request"""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeCookbookAI:
        fake = self

        async def get_response(self, prompt, message, *, response_schema, attachments=None, provider=None, task=None):
            fake.calls.append((response_schema.__name__, len(attachments or [])))
            fake.tasks.append((response_schema.__name__, task))
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
        "Recipes found in the cookbook: 3, across 5 pages",
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
        assert recipe["extras"] == {"pdf_source": f"{cookbook.fingerprint}#page={page}#item=0"}

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
        "Recipes found in the cookbook: 3, across 5 pages",
        "Already imported from this cookbook, so skipped: 3",
    ]
    assert ai.requests_for(OpenAIRecipe) == []

    # nothing was imported twice, and there's still just the one cookbook
    r = api_client.get(api_routes.recipes_slug(f"{slugify(cookbook.names[0])}-1"), headers=unique_user.token)
    assert r.status_code == 404
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert [cookbook["name"] for cookbook in cookbooks].count(book_name) == 1


def test_import_pdf_that_imports_nothing_adds_no_cookbook(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.usage_limit_on = cookbook.names[0]
    book_name = random_string()

    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "failure"

    # an empty cookbook would show nothing, so it's only added once a recipe is in
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert book_name not in [cookbook["name"] for cookbook in cookbooks]

    ai.usage_limit_on = None
    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"

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
        "Already imported from this cookbook, so skipped: 1",
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
        "No recipes were found in the cookbook",
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
    assert [entry["message"] for entry in report["entries"]] == ["No recipes were found in the cookbook"]
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


def test_import_pdf_asks_for_each_cookbook_task(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    ai.organizers = OpenAIOrganizers(tags=[], categories=[], tools=[])

    r = import_pdf(api_client, unique_user, cookbook.path, name=random_string(), addOrganizers="true")

    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
    assert set(ai.tasks) == {
        (OpenAIPdfRecipeLocations.__name__, AITask.cookbook_discovery),
        (OpenAIRecipe.__name__, AITask.cookbook_extraction),
        (OpenAIOrganizers.__name__, AITask.organizer_matching),
    }


def test_import_pdf_reads_page_images_only_for_the_task_that_has_an_image_provider(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    repo = unique_user.repos.group_ai_provider_settings
    settings = repo.get_one(unique_user.repos.group_id)
    # No group image provider, but reading each recipe has one of its own
    repo.update(
        unique_user.repos.group_id,
        {
            "default_provider_id": settings.default_provider_id,
            "audio_provider_id": None,
            "image_provider_id": None,
            "task_settings": [
                AITaskSettingUpdate(task=AITask.cookbook_extraction, image_provider_id=settings.default_provider_id)
            ],
        },
    )
    try:
        r = import_pdf(api_client, unique_user, cookbook.path, name=random_string())

        assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
        # finding recipes is text only, and reading them sends the page images
        assert set(ai.requests_for(OpenAIPdfRecipeLocations)) == {0}
        assert all(attachments > 0 for attachments in ai.requests_for(OpenAIRecipe))
    finally:
        repo.update(unique_user.repos.group_id, {"image_provider_id": settings.image_provider_id, "task_settings": []})


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


class EpubCookbookFile:
    """A small cookbook EPUB: a cover, a contents chapter, and a chapter of three recipes, one with a photo."""

    def __init__(self, path: Path) -> None:
        self.recipes = [random_string() for _ in range(3)]
        pancakes, waffles, omelette = self.recipes
        photo = EpubImageSpec(name="pancakes.jpg", width=800, height=600)

        def recipe(name: str) -> str:
            return f"<h2>{name.upper()}</h2><h3>INGREDIENTS</h3><ul><li>2 eggs</li></ul><h3>INSTRUCTIONS</h3>"

        self.path = build_epub(
            path,
            [
                EpubChapterSpec("<h1>BREAKFAST BOOK</h1>"),
                EpubChapterSpec("<h1>CONTENTS</h1>" + "".join(f"<p>{name}</p>" for name in self.recipes)),
                EpubChapterSpec(
                    f'<img src="../images/pancakes.jpg"/>{recipe(pancakes)}{recipe(waffles)}{recipe(omelette)}',
                    images=[photo],
                ),
            ],
        )

    @property
    def names(self) -> list[str]:
        return [name.title() for name in self.recipes]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def test_import_epub_creates_every_recipe(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    ai = FakeCookbookAI().install(monkeypatch)
    epub = EpubCookbookFile(tmp_path.joinpath("breakfast.epub"))
    book_name = random_string()

    with epub.path.open("rb") as f:
        r = api_client.post(
            api_routes.recipes_create_pdf,
            data={"name": book_name},
            files=[("file", (epub.path.name, f, "application/epub+zip"))],
            headers=unique_user.token,
        )
    assert r.status_code == 202

    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]] == [
        "Recipes found in the cookbook: 3, across 5 pages",
        *(f"Imported {name} (page {page})" for name, page in zip(epub.names, [3, 4, 5], strict=True)),
    ]

    # an EPUB's text is in reading order, so the AI is sent no page images, even with an image provider
    assert ai.requests_for(OpenAIPdfRecipeLocations) == [0]
    assert ai.requests_for(OpenAIRecipe) == [0, 0, 0]

    for name, page in zip(epub.names, [3, 4, 5], strict=True):
        recipe = get_recipe(api_client, unique_user, name)
        assert [tag["name"] for tag in recipe["tags"]] == [book_name]
        # its pages don't match any ebook reader's, so the note names just the book
        source_note = recipe["notes"][-1]
        assert (source_note["title"], source_note["text"]) == ("Source", book_name)
        assert recipe["extras"] == {"pdf_source": f"{epub.fingerprint}#page={page}#item=0"}

    # the photo before the first recipe's title is that recipe's
    assert get_recipe(api_client, unique_user, epub.names[0])["image"]
    assert not get_recipe(api_client, unique_user, epub.names[1])["image"]

    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert [cookbook["name"] for cookbook in cookbooks].count(book_name) == 1

    # and importing it again skips them all
    ai.calls.clear()
    with epub.path.open("rb") as f:
        r = api_client.post(
            api_routes.recipes_create_pdf, files=[("file", ("breakfast.epub", f))], headers=unique_user.token
        )
    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert [entry["message"] for entry in report["entries"]][1:] == [
        "Already imported from this cookbook, so skipped: 3"
    ]
    assert ai.requests_for(OpenAIRecipe) == []


def test_import_pdf_rejects_files_that_arent_pdfs(api_client: TestClient, unique_user: TestUser, tmp_path: Path):
    not_a_pdf = tmp_path.joinpath("recipes.pdf")
    not_a_pdf.write_text("Pancakes: 2 eggs, cook them.")

    r = import_pdf(api_client, unique_user, not_a_pdf)

    assert r.status_code == 400
    assert r.json()["detail"]["message"].startswith("That file isn't a PDF or EPUB Mealie can read")


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


def test_import_epub_too_large_to_be_a_real_book_is_rejected(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(epub_document, "MAX_DOCUMENT_BYTES", 10_000)
    epub = build_epub(
        tmp_path.joinpath("bomb.epub"),
        [EpubChapterSpec("<h2>Pancakes</h2><p>" + " " * 100_000 + "</p>")],
        compress=True,
    )

    r = import_pdf(api_client, unique_user, epub)

    assert r.status_code == 400
    assert r.json()["detail"]["message"].startswith("That file isn't a PDF or EPUB Mealie can read")


def test_import_pdf_tells_the_cookbook_it_couldnt_add_and_adds_it_next_time(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    book_name = random_string()
    broken = {"cookbooks": True}
    create = RepositoryCookbooks.create

    def create_cookbook(self, data):
        if broken["cookbooks"]:
            raise Exception("database is locked")
        return create(self, data)

    monkeypatch.setattr(RepositoryCookbooks, "create", create_cookbook)

    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    # the recipes are all in, and the report says the cookbook isn't
    assert report["status"] == "partial"
    messages = [entry["message"] for entry in report["entries"]]
    assert [f"Imported {name} (page {page})" for name, page in zip(cookbook.names, [3, 4, 5], strict=True)] == [
        message for message in messages if message.startswith("Imported")
    ]
    [failed] = [entry for entry in report["entries"] if not entry["success"]]
    assert failed["message"].startswith(f"Couldn't add the {book_name} cookbook, though its recipes are imported")
    assert failed["exception"] == "database is locked"
    assert len(ai.requests_for(OpenAIRecipe)) == 3
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert book_name not in [cookbook["name"] for cookbook in cookbooks]

    # importing it again, with nothing left to import, adds it
    broken["cookbooks"] = False
    ai.calls.clear()
    r = import_pdf(api_client, unique_user, cookbook.path, name=book_name)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]][1:] == [
        "Already imported from this cookbook, so skipped: 3"
    ]
    assert ai.calls == []
    cookbooks = api_client.get(api_routes.households_cookbooks, headers=unique_user.token).json()["items"]
    assert [cookbook["name"] for cookbook in cookbooks].count(book_name) == 1


class SharedPageBook:
    """A cookbook with two recipes printed on the one page, as a PDF or an EPUB."""

    def __init__(self, tmp_path: Path, format: str) -> None:
        self.names = [random_string().title(), random_string().title()]
        if format == "epub":
            self.path = build_epub(
                tmp_path.joinpath("shared.epub"),
                [EpubChapterSpec("".join(f"<h3>{name}</h3><p>INGREDIENTS</p><p>2 eggs</p>" for name in self.names))],
            )
        else:
            self.path = build_pdf(
                tmp_path.joinpath("shared.pdf"), [PdfPageSpec(lines=[*self.names, "INGREDIENTS", "2 eggs"])]
            )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def source(self, suffix: str) -> str:
        return f"{self.fingerprint}#page=1{suffix}"


def find_on_first_page(ai: FakeCookbookAI, monkeypatch: pytest.MonkeyPatch, names: list[str]) -> None:
    """Has the AI find recipes with these names on the first page, whatever the pages say."""

    recipes = [OpenAIPdfRecipeLocation(name=name, first_page=1, last_page=1) for name in names]
    monkeypatch.setattr(ai, "find", lambda message: OpenAIPdfRecipeLocations(recipes=recipes))


def update_recipe(api_client: TestClient, user: TestUser, recipe: dict, **changes) -> dict:
    slug = recipe["slug"]
    recipe = {**recipe, **changes}
    r = api_client.put(api_routes.recipes_slug(slug), headers=user.token, json=recipe)
    assert r.status_code == 200
    return r.json()


def forget_the_books_recipes(user: TestUser, fingerprint: str) -> None:
    """Deletes what was saved about the recipes in a book, as if it had been imported before that was saved."""

    saved = user.repos.cookbook_imports.get_one(fingerprint, key="fingerprint")
    assert saved
    user.repos.cookbook_imports.delete(saved.id)


def pdf_sources(user: TestUser, fingerprint: str) -> list[str]:
    return sorted(user.repos.recipes.get_extras_values("pdf_source", f"{fingerprint}#page="))


@pytest.mark.parametrize("format", ["pdf", "epub"])
@pytest.mark.parametrize("failure", ["usage-limit", "fails-twice"])
def test_import_again_picks_up_recipes_on_a_shared_page_whatever_the_ai_calls_them_now(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    format: str,
    failure: str,
):
    book = SharedPageBook(tmp_path, format)
    ai = FakeCookbookAI().install(monkeypatch)
    find_on_first_page(ai, monkeypatch, book.names)
    if failure == "usage-limit":
        ai.usage_limit_on = book.names[1]
    else:
        ai.flaky[book.names[1]] = 2

    r = import_pdf(api_client, unique_user, book.path)
    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "partial"
    first = get_recipe(api_client, unique_user, book.names[0])
    assert first["extras"] == {"pdf_source": book.source("#item=0")}

    # the recipe is renamed, and asked again, the AI would name and count the recipes differently
    update_recipe(api_client, unique_user, first, name=random_string())
    find_on_first_page(ai, monkeypatch, [random_string().title() for _ in range(3)])
    ai.usage_limit_on = None
    ai.flaky.clear()
    ai.calls.clear()

    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert sorted(entry["message"] for entry in report["entries"]) == sorted(
        [
            "Recipes found in the cookbook: 2, across 1 pages",
            "Already imported from this cookbook, so skipped: 1",
            f"Imported {book.names[1]} (page 1)",
        ]
    )
    # the recipes found the first time are used again, so the AI isn't asked to find them
    assert ai.requests_for(OpenAIPdfRecipeLocations) == []
    assert len(ai.requests_for(OpenAIRecipe)) == 1
    assert get_recipe(api_client, unique_user, book.names[1])["extras"] == {"pdf_source": book.source("#item=1")}

    ai.calls.clear()
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["status"] == "success"
    assert "Already imported from this cookbook, so skipped: 2" in [entry["message"] for entry in report["entries"]]
    assert ai.calls == []
    assert pdf_sources(unique_user, book.fingerprint) == [book.source("#item=0"), book.source("#item=1")]


class SimulatedRestart(BaseException):
    """Stands in for Mealie stopping partway through an import. It isn't an `Exception`, so nothing handles it."""


@pytest.mark.parametrize("format", ["pdf", "epub"])
def test_import_interrupted_partway_through_a_shared_page_picks_up_where_it_left_off(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, format: str
):
    book = SharedPageBook(tmp_path, format)
    ai = FakeCookbookAI().install(monkeypatch)
    find_on_first_page(ai, monkeypatch, book.names)
    build = ai.build

    def build_until_the_restart(message: str) -> OpenAIRecipe:
        if message.startswith(f"Recipe: {book.names[1]}"):
            raise SimulatedRestart()
        return build(message)

    monkeypatch.setattr(ai, "build", build_until_the_restart)
    with pytest.raises(SimulatedRestart):
        import_pdf(api_client, unique_user, book.path)
    close_interrupted_imports()
    assert get_recipe(api_client, unique_user, book.names[0])

    monkeypatch.setattr(ai, "build", build)
    find_on_first_page(ai, monkeypatch, [random_string().title(), random_string().title()])
    ai.calls.clear()
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert sorted(entry["message"] for entry in report["entries"]) == sorted(
        [
            "Recipes found in the cookbook: 2, across 1 pages",
            "Already imported from this cookbook, so skipped: 1",
            f"Imported {book.names[1]} (page 1)",
        ]
    )
    assert ai.requests_for(OpenAIPdfRecipeLocations) == []
    assert pdf_sources(unique_user, book.fingerprint) == [book.source("#item=0"), book.source("#item=1")]


@pytest.mark.parametrize("format", ["pdf", "epub"])
@pytest.mark.parametrize("older_marker", ["page", "name"])
def test_import_again_matches_recipes_from_older_imports_by_name(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    format: str,
    older_marker: str,
):
    book = SharedPageBook(tmp_path, format)
    ai = FakeCookbookAI().install(monkeypatch)
    find_on_first_page(ai, monkeypatch, book.names)
    ai.usage_limit_on = book.names[1]
    import_pdf(api_client, unique_user, book.path)

    # as an older import would have left it, before the recipes found in a book were saved
    first = get_recipe(api_client, unique_user, book.names[0])
    forget_the_books_recipes(unique_user, book.fingerprint)
    if older_marker == "page":
        update_recipe(api_client, unique_user, first, extras={"pdf_source": book.source("")})
    else:
        # some recorded the name the AI found, which matches even once the recipe's renamed
        update_recipe(
            api_client,
            unique_user,
            first,
            name=random_string(),
            extras={"pdf_source": book.source(f"#recipe={slugify(book.names[0])}")},
        )

    ai.usage_limit_on = None
    ai.calls.clear()
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert sorted(entry["message"] for entry in report["entries"]) == sorted(
        [
            "Recipes found in the cookbook: 2, across 1 pages",
            "Already imported from this cookbook, so skipped: 1",
            f"Imported {book.names[1]} (page 1)",
        ]
    )
    assert len(ai.requests_for(OpenAIRecipe)) == 1

    # from then on, the recipes found are saved, so the AI's names no longer matter
    find_on_first_page(ai, monkeypatch, [random_string().title()])
    ai.calls.clear()
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["status"] == "success"
    assert "Already imported from this cookbook, so skipped: 2" in [entry["message"] for entry in report["entries"]]
    assert ai.calls == []
    assert len(pdf_sources(unique_user, book.fingerprint)) == 2


def test_import_again_skips_renamed_recipes_from_older_imports_and_says_so(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    import_pdf(api_client, unique_user, cookbook.path)

    # as older imports left them: one recipe per page, recorded by page alone, and since renamed
    forget_the_books_recipes(unique_user, cookbook.fingerprint)
    for name, page in zip(cookbook.names, [3, 4, 5], strict=True):
        recipe = get_recipe(api_client, unique_user, name)
        update_recipe(
            api_client,
            unique_user,
            recipe,
            name=random_string(),
            extras={"pdf_source": f"{cookbook.fingerprint}#page={page}"},
        )

    ai.calls.clear()
    r = import_pdf(api_client, unique_user, cookbook.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    # a page's recipes are no more than the recipes imported from it, so they're all in
    assert report["status"] == "success"
    assert sorted(entry["message"] for entry in report["entries"]) == sorted(
        [
            "Recipes found in the cookbook: 3, across 5 pages",
            "Already imported from this cookbook, so skipped: 3",
            *(
                f"Taken to be imported before under other names, so skipped (page {page}): {name}"
                for name, page in zip(cookbook.names, [3, 4, 5], strict=True)
            ),
        ]
    )
    assert ai.requests_for(OpenAIRecipe) == []
    assert len(pdf_sources(unique_user, cookbook.fingerprint)) == 3


@pytest.mark.parametrize("older_marker", ["page", "item-without-saved-recipes"])
def test_import_again_leaves_out_and_reports_recipes_it_cant_tell_were_imported(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, older_marker: str
):
    book = SharedPageBook(tmp_path, "pdf")
    ai = FakeCookbookAI().install(monkeypatch)
    find_on_first_page(ai, monkeypatch, book.names)
    ai.usage_limit_on = book.names[1]
    import_pdf(api_client, unique_user, book.path)

    # one of the page's two recipes was imported, but neither its marker nor its name says which
    first = get_recipe(api_client, unique_user, book.names[0])
    forget_the_books_recipes(unique_user, book.fingerprint)
    extras = {"pdf_source": book.source("")} if older_marker == "page" else first["extras"]
    first = update_recipe(api_client, unique_user, first, name=random_string(), extras=extras)

    ai.usage_limit_on = None
    ai.calls.clear()
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "partial"
    [left_out] = [entry for entry in report["entries"] if not entry["success"]]
    assert left_out["message"].startswith(
        "Couldn't tell which recipes on page 1 were imported before, so these were left out rather than risk "
        f"importing one twice: {book.names[0]}, {book.names[1]}."
    )
    assert ai.requests_for(OpenAIRecipe) == []
    # a marker numbered among recipes that are gone is now just its page, so it's never trusted again
    assert pdf_sources(unique_user, book.fingerprint) == [book.source("")]

    # and it says the same the next time
    r = import_pdf(api_client, unique_user, book.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])
    assert report["status"] == "partial"
    assert ai.requests_for(OpenAIRecipe) == []

    # doing what it says imports them both
    r = api_client.delete(api_routes.recipes_slug(first["slug"]), headers=unique_user.token)
    assert r.status_code == 200
    r = import_pdf(api_client, unique_user, book.path)
    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
    assert pdf_sources(unique_user, book.fingerprint) == [book.source("#item=0"), book.source("#item=1")]


def test_import_again_finds_the_recipes_afresh_once_none_of_them_are_left(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    ai = FakeCookbookAI().install(monkeypatch)
    import_pdf(api_client, unique_user, cookbook.path)
    for name in cookbook.names:
        api_client.delete(api_routes.recipes_slug(slugify(name)), headers=unique_user.token)

    ai.calls.clear()
    r = import_pdf(api_client, unique_user, cookbook.path)

    assert get_report(api_client, unique_user, r.json()["reportId"])["status"] == "success"
    assert len(ai.requests_for(OpenAIPdfRecipeLocations)) == 1
    assert len(ai.requests_for(OpenAIRecipe)) == 3


def test_import_again_looks_through_the_pages_it_couldnt_before(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, cookbook: Cookbook
):
    monkeypatch.setattr(pdf_import_service, "INDEX_MAX_PAGES", 3)
    monkeypatch.setattr(pdf_import_service, "INDEX_OVERLAP_PAGES", 0)
    ai = FakeCookbookAI().install(monkeypatch)
    ai.find_failures = 2

    r = import_pdf(api_client, unique_user, cookbook.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    # pages 1 to 3 couldn't be looked through, so the recipe on page 3 is still to come
    assert report["status"] == "partial"
    assert [entry["message"] for entry in report["entries"]] == [
        "Couldn't look for recipes on pages 1 to 3",
        "Recipes found in the cookbook: 2, across 5 pages",
        f"Imported {cookbook.names[1]} (page 4)",
        f"Imported {cookbook.names[2]} (page 5)",
    ]

    ai.calls.clear()
    r = import_pdf(api_client, unique_user, cookbook.path)
    report = get_report(api_client, unique_user, r.json()["reportId"])

    assert report["status"] == "success"
    assert [entry["message"] for entry in report["entries"]] == [
        "Recipes found in the cookbook: 3, across 5 pages",
        "Already imported from this cookbook, so skipped: 2",
        f"Imported {cookbook.names[0]} (page 3)",
    ]
    # just the pages it couldn't look through before
    assert ai.requests_for(OpenAIPdfRecipeLocations) == [0]
    assert len(ai.requests_for(OpenAIRecipe)) == 1
