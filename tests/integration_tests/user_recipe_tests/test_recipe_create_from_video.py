import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mealie.services.openai.transcription as transcription_module
import mealie.services.scraper.recipe_scraper as recipe_scraper_module
from mealie.core import exceptions
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
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

    assert len(messages) == 1
    assert video.captions in messages[0]
    assert video.description in messages[0]

    recipe = api_client.get(api_routes.recipes_slug(json.loads(r.text)), headers=unique_user.token).json()
    assert recipe["name"] == openai_recipe.name
    assert recipe["orgURL"] == VIDEO_URL
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
