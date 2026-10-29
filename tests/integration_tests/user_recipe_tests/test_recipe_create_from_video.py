import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

import mealie.services.openai.transcription as transcription_module
import mealie.services.recipe.import_workflow.compilers.transcription as compiler_module
import mealie.services.scraper.recipe_scraper as recipe_scraper_module
from mealie.core import exceptions
from mealie.pkgs.safehttp import FetchResult
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.openai.recipe import OpenAIRecipe, OpenAIRecipeIngredient, OpenAIRecipeInstruction
from mealie.services.openai import OpenAIService
from mealie.services.openai.transcription import VideoInfo
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.scraper.scraper_strategies import RecipeScraperOpenAI
from tests.utils import api_routes
from tests.utils.factories import random_int, random_string
from tests.utils.fixture_schemas import TestUser

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# What YouTube serves for a video: its title, and structured data for the video rather than a recipe
VIDEO_PAGE = (
    "<html><head><title>Foolproof Pan Pizza - YouTube</title>"
    '<meta property="og:title" content="Foolproof Pan Pizza">'
    '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "VideoObject"}</script>'
    "</head><body></body></html>"
)


@pytest.fixture(autouse=True)
def default_provider(unique_user: TestUser) -> Generator[None]:
    """Only a default provider, like a group whose one provider is a ChatGPT plan"""

    provider = unique_user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="gpt-4o", api_key="test-key")
    )
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=provider.id, audio_provider_id=None, image_provider_id=None),
    )

    yield

    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=None, audio_provider_id=None, image_provider_id=None),
    )


@pytest.fixture(autouse=True)
def video_page(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(compiler_module, "resilient_fetch", AsyncMock(return_value=None))

    async def mock_safe_scrape_html(url: str) -> str:
        return VIDEO_PAGE

    monkeypatch.setattr(recipe_scraper_module, "safe_scrape_html", mock_safe_scrape_html)


@pytest.fixture(autouse=True)
def no_image_downloads(monkeypatch: pytest.MonkeyPatch):
    async def mock_scrape_image(*_, **__) -> str:
        return "TEST_IMAGE"

    monkeypatch.setattr(RecipeDataService, "scrape_image", mock_scrape_image)


@pytest.fixture()
def video(monkeypatch: pytest.MonkeyPatch) -> VideoInfo:
    """The video yt-dlp reads for any URL, which tests adjust before importing it"""

    info = VideoInfo(
        title="Foolproof Pan Pizza",
        description=random_string(),
        thumbnail_url="https://example.com/thumbnail.jpg",
        captions=random_string(),
        can_download=True,
    )
    monkeypatch.setattr(transcription_module, "read_video", lambda url: info)
    return info


@pytest.fixture()
def openai_recipe() -> OpenAIRecipe:
    return OpenAIRecipe(
        name=random_string(),
        description=random_string(),
        ingredients=[OpenAIRecipeIngredient(text=random_string()) for _ in range(random_int(2, 5))],
        instructions=[OpenAIRecipeInstruction(text=random_string()) for _ in range(random_int(2, 5))],
    )


@pytest.fixture()
def messages(monkeypatch: pytest.MonkeyPatch, openai_recipe: OpenAIRecipe) -> list[str]:
    """What's sent to the AI provider, which replies to every request with `openai_recipe`"""

    sent: list[str] = []

    async def mock_get_response(self, prompt, message, *args, response_schema=None, **kwargs):
        sent.append(message)
        if response_schema is OpenAIOrganizers:
            return OpenAIOrganizers(categories=["Main Dish"])
        return openai_recipe if response_schema is OpenAIRecipe else None

    monkeypatch.setattr(OpenAIService, "get_response", mock_get_response)
    return sent


def _import(api_client: TestClient, user: TestUser):
    return api_client.post(api_routes.recipes_create_url, json={"url": VIDEO_URL}, headers=user.token)


def test_create_recipe_from_video(
    api_client: TestClient,
    unique_user: TestUser,
    video: VideoInfo,
    openai_recipe: OpenAIRecipe,
    messages: list[str],
):
    r = _import(api_client, unique_user)
    assert r.status_code == 201

    assert len(messages) == 2  # Extract once, then classify using the original video context.
    assert video.captions in messages[0]
    assert video.description in messages[0]
    assert video.captions in messages[1]

    recipe = api_client.get(api_routes.recipes_slug(json.loads(r.text)), headers=unique_user.token).json()
    assert recipe["name"] == openai_recipe.name
    assert recipe["orgURL"] == VIDEO_URL
    assert [category["name"] for category in recipe["recipeCategory"]] == ["Main Dish"]
    assert len(recipe["recipeIngredient"]) == len(openai_recipe.ingredients)
    assert len(recipe["recipeInstructions"]) == len(openai_recipe.instructions)


def test_create_recipe_from_video_without_captions_or_audio_provider(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    video: VideoInfo,
    messages: list[str],
):
    """Plenty of short videos write their recipe in the description"""

    video.captions = ""

    def fail_if_downloaded(url: str, temp_path: Path) -> Path:
        raise AssertionError("there's no audio provider to transcribe the audio")

    monkeypatch.setattr(transcription_module, "download_audio", fail_if_downloaded)

    r = _import(api_client, unique_user)
    assert r.status_code == 201
    assert video.description in messages[0]
    assert "## Video transcript" not in messages[0]


def test_create_recipe_from_video_transcribes_one_without_captions(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    video: VideoInfo,
    messages: list[str],
):
    settings = unique_user.repos.group_ai_provider_settings.get_one(unique_user.repos.group_id)
    assert settings
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=settings.default_provider_id,
            audio_provider_id=settings.default_provider_id,
            image_provider_id=None,
        ),
    )

    video.captions = ""
    transcript = random_string()

    def mock_download_audio(url: str, temp_path: Path) -> Path:
        assert url == VIDEO_URL
        return temp_path / "audio.mp3"

    async def mock_transcribe_audio(self, audio_file_path: Path) -> str:
        return transcript

    monkeypatch.setattr(transcription_module, "download_audio", mock_download_audio)
    monkeypatch.setattr(OpenAIService, "transcribe_audio", mock_transcribe_audio)

    r = _import(api_client, unique_user)
    assert r.status_code == 201
    assert f"## Video transcript\n\n{transcript}" in messages[0]


@pytest.fixture()
def video_strategy_only(monkeypatch: pytest.MonkeyPatch):
    """
    Leaves only the strategy that reads videos, so a failure isn't covered up by the Open Graph
    strategy, which saves a placeholder recipe from the page's title rather than fail
    """

    monkeypatch.setattr(recipe_scraper_module, "DEFAULT_SCRAPER_STRATEGIES", [RecipeScraperOpenAI])


@pytest.mark.usefixtures("video_strategy_only")
def test_create_recipe_from_video_ai_disabled(api_client: TestClient, unique_user: TestUser, video: VideoInfo):
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=None, audio_provider_id=None, image_provider_id=None),
    )

    r = _import(api_client, unique_user)
    assert r.status_code == 400


@pytest.mark.usefixtures("video_strategy_only")
def test_create_recipe_from_video_download_error(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    messages: list[str],
):
    def mock_read_video(url: str) -> VideoInfo:
        raise exceptions.VideoDownloadError("Mock video download error")

    monkeypatch.setattr(transcription_module, "read_video", mock_read_video)

    r = _import(api_client, unique_user)
    assert r.status_code == 400
    assert messages == []


@pytest.mark.usefixtures("video_strategy_only")
def test_create_recipe_from_video_transcription_error(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    video: VideoInfo,
    messages: list[str],
):
    settings = unique_user.repos.group_ai_provider_settings.get_one(unique_user.repos.group_id)
    assert settings
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=settings.default_provider_id,
            audio_provider_id=settings.default_provider_id,
            image_provider_id=None,
        ),
    )

    video.captions = ""

    async def mock_transcribe_audio(self, audio_file_path: Path) -> str | None:
        raise Exception("Mock transcribe audio exception")

    monkeypatch.setattr(transcription_module, "download_audio", lambda url, temp_path: temp_path / "audio.mp3")
    monkeypatch.setattr(OpenAIService, "transcribe_audio", mock_transcribe_audio)

    r = _import(api_client, unique_user)
    assert r.status_code == 400
    assert messages == []


@pytest.mark.usefixtures("video_strategy_only")
def test_create_recipe_from_video_empty_openai_response(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    video: VideoInfo,
):
    async def mock_get_response(self, prompt, message, *args, **kwargs) -> OpenAIRecipe | None:
        return None

    monkeypatch.setattr(OpenAIService, "get_response", mock_get_response)

    r = _import(api_client, unique_user)
    assert r.status_code == 400


INSTAGRAM_URL = "https://www.instagram.com/reel/C66-jHYy5_k/"


def _import_url(api_client: TestClient, user: TestUser, url: str):
    return api_client.post(api_routes.recipes_create_url, json={"url": url}, headers=user.token)


def _message(response) -> str:
    return response.json()["detail"]["message"]


def test_a_video_post_is_never_saved_as_a_placeholder(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, video: VideoInfo
):
    """A video site's page is only the post's caption, so a failed read is reported, not saved from the page"""

    async def mock_get_response(self, prompt, message, *args, **kwargs) -> OpenAIRecipe | None:
        return None

    monkeypatch.setattr(OpenAIService, "get_response", mock_get_response)

    r = _import_url(api_client, unique_user, INSTAGRAM_URL)
    assert r.status_code == 400


def test_video_import_does_not_use_placeholder_page_scraper(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    video: VideoInfo,
    messages: list[str],
):
    fetched: list[str] = []

    async def mock_safe_scrape_html(url: str) -> str:
        fetched.append(url)
        return VIDEO_PAGE

    monkeypatch.setattr(recipe_scraper_module, "safe_scrape_html", mock_safe_scrape_html)

    r = _import_url(api_client, unique_user, INSTAGRAM_URL)
    assert r.status_code == 201
    assert fetched == []
    assert video.description in messages[0]


@pytest.mark.parametrize("organize", [True, False])
def test_instagram_import_saves_video_link_and_source_category(
    api_client: TestClient, unique_user: TestUser, video: VideoInfo, messages: list[str], organize: bool
) -> None:
    response = api_client.post(
        api_routes.recipes_create_url,
        json={"url": INSTAGRAM_URL, "organize": organize},
        headers=unique_user.token,
    )
    assert response.status_code == 201
    recipe = api_client.get(api_routes.recipes_slug(response.json()), headers=unique_user.token).json()
    assert recipe["orgURL"] == INSTAGRAM_URL
    categories = [category["name"] for category in recipe["recipeCategory"]]
    assert categories.count("Instagram") == 1
    if organize:
        assert "Main Dish" in categories
    else:
        assert categories == ["Instagram"]


def test_instagram_caption_amounts_and_sections_survive_import(
    api_client: TestClient, unique_user: TestUser, video: VideoInfo, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.instagram.com/p/DS66ymegPwK/"
    page = Path("tests/data/html/instagram-recipe-caption.html").read_text()
    monkeypatch.setattr(
        compiler_module,
        "resilient_fetch",
        AsyncMock(return_value=FetchResult(page.encode(), 200, url, httpx.Headers(), "utf-8")),
    )
    video.description = ""
    video.captions = "Add garlic and ginger, then the coconut milk. Brown the beef and cook the noodles."
    # Expected lines include repeated ingredients in separate sections and unquantified toppings.
    sections = {
        "For the Miso Curry Broth:": [
            "2 tbsp oil",
            "6 cloves garlic, minced",
            "2 tsp ginger, minced",
            "1 tbsp lemongrass",
            "2 tbsp curry paste",
            "1 tbsp miso paste",
            "1 can coconut milk (400 mL)",
            "2 cups chicken broth",
            "2 tbsp CHIN-SU fish sauce",
            "1 tbsp or more of CHIN-SU hot sauce (adjust to your preference)",
            "1 tbsp sugar",
            "4 kaffir lime leaves",
            "2 portions instant ramen noodles",
        ],
        "For the Beef Topping:": [
            "500 g beef mince",
            "1 tbsp oil for cooking",
            "3 cloves garlic, minced",
            "1/2 shallot, minced",
            "2 tsp ginger, minced",
            "2 tsp soy sauce",
            "1 tsp dark soy sauce",
            "1 tbsp CHIN-SU fish sauce",
            "1 tsp sugar",
        ],
        "Toppings:": ["Soft-boiled egg", "Sliced green onions", "Sesame seeds", "CHIN-SU Hot sauce"],
    }
    ingredients = [
        OpenAIRecipeIngredient(title=title if index == 0 else None, text=line)
        for title, lines in sections.items()
        for index, line in enumerate(lines)
    ]

    async def response(self, prompt, message, *args, response_schema=None, **kwargs):
        assert response_schema is OpenAIRecipe
        for title, lines in sections.items():
            assert title in message
            assert all(line in message for line in lines)
        return OpenAIRecipe(name=random_string(), ingredients=ingredients)

    monkeypatch.setattr(OpenAIService, "get_response", response)
    result = api_client.post(
        api_routes.recipes_create_url, json={"url": url, "organize": False}, headers=unique_user.token
    )
    assert result.status_code == 201
    recipe = api_client.get(api_routes.recipes_slug(result.json()), headers=unique_user.token).json()
    assert [(ing["title"], ing["note"]) for ing in recipe["recipeIngredient"]] == [
        (ing.title, ing.text) for ing in ingredients
    ]
    assert recipe["orgURL"] == url
    assert any(category["name"] == "Instagram" for category in recipe["recipeCategory"])


def test_a_video_post_without_ai_says_it_needs_a_provider(
    api_client: TestClient, unique_user: TestUser, video: VideoInfo
):
    unique_user.repos.group_ai_provider_settings.update(
        unique_user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=None, audio_provider_id=None, image_provider_id=None),
    )

    r = _import_url(api_client, unique_user, INSTAGRAM_URL)
    assert r.status_code == 400
    assert "needs an AI provider" in _message(r)


def test_a_post_without_its_recipe_says_where_to_look(
    api_client: TestClient, unique_user: TestUser, monkeypatch: pytest.MonkeyPatch, video: VideoInfo
):
    """A teaser post ("full recipe at the link in our bio") has nothing to build a recipe from"""

    video.captions = ""
    video.description = "FAJITA BOMBS 💕 Full recipe can be found via the link in our bio"

    async def mock_get_response(self, prompt, message, *args, response_schema=None, **kwargs):
        return OpenAIRecipe(name="Fajita Bombs", ingredients=[], instructions=[])

    monkeypatch.setattr(OpenAIService, "get_response", mock_get_response)

    r = _import_url(api_client, unique_user, INSTAGRAM_URL)
    assert r.status_code == 400
    assert "link in their bio" in _message(r)


def test_an_imported_recipe_without_steps_points_to_its_source(
    api_client: TestClient, unique_user: TestUser, video: VideoInfo, messages: list[str], openai_recipe: OpenAIRecipe
):
    """Ingredients in the caption, steps in a comment: the editor's sample step would read as the recipe's"""

    openai_recipe.instructions = []

    r = _import_url(api_client, unique_user, INSTAGRAM_URL)
    assert r.status_code == 201

    recipe = api_client.get(api_routes.recipes_slug(r.json()), headers=unique_user.token).json()
    assert recipe["recipeInstructions"] == []
    assert len(recipe["recipeIngredient"]) == len(openai_recipe.ingredients)
    steps_note = recipe["notes"][-1]
    assert steps_note["title"] == "Steps"
    assert INSTAGRAM_URL.rstrip("/") in steps_note["text"]
