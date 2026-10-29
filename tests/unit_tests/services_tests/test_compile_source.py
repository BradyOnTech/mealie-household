import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import mealie.services.recipe.import_workflow.steps.compile_source as compile_source_module
from mealie.core import exceptions
from mealie.pkgs.safehttp.fetch import FetchResult
from mealie.schema.openai.compiled_source import OpenAICompiledSource
from mealie.services.openai import transcription
from mealie.services.openai.transcription import VideoInfo
from mealie.services.recipe.import_workflow.compilers import TranscriptionCompiler
from mealie.services.recipe.import_workflow.compilers.base import SourceCompiler, SourceType
from mealie.services.recipe.import_workflow.context import WorkflowContext, WorkflowInput, WorkflowOptions
from mealie.services.recipe.import_workflow.exceptions import NoRecipeDataError
from mealie.services.recipe.import_workflow.steps.compile_source import CompileSourceStep

FACEBOOK_SHARE_URL = "https://www.facebook.com/share/r/1DWziuVHRi/"
FACEBOOK_REEL_URL = "https://www.facebook.com/reel/1433866715330175/"
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
NYT_COOKING_URL = "https://cooking.nytimes.com/recipes/1015819-chocolate-chip-cookies"


def html_fetch_result(html: str, url: str) -> FetchResult:
    return FetchResult(html.encode(), 200, url, httpx.Headers(), "utf-8")


def _ctx(url: str) -> WorkflowContext:
    ai = MagicMock()
    ai.provider_settings.audio_provider_enabled = False
    translator = MagicMock()
    translator.t.side_effect = lambda key: key
    return WorkflowContext(
        input=WorkflowInput(url=url),
        options=WorkflowOptions(),
        repos=MagicMock(),
        translator=translator,
        ai=ai,
        on_progress=AsyncMock(),
    )


@pytest.fixture()
def read_videos(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every URL yt-dlp is asked to read, each of which reads as a video with captions"""

    read: list[str] = []

    def mock_read_video(url: str) -> VideoInfo:
        read.append(url)
        return VideoInfo(title="A video", captions="mix flour and water", can_download=True)

    monkeypatch.setattr(transcription, "read_video", mock_read_video)
    return read


@pytest.fixture()
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every page fetched, each of which serves a Facebook reel that has no recipe of its own"""

    urls: list[str] = []

    async def mock_resilient_fetch(url: str) -> FetchResult:
        urls.append(url)
        return html_fetch_result("<html>facebook</html>", FACEBOOK_REEL_URL)

    monkeypatch.setattr(compile_source_module, "resilient_fetch", mock_resilient_fetch)
    return urls


@pytest.mark.asyncio
async def test_share_url_is_compiled_as_video_after_redirect(read_videos: list[str], fetched: list[str]):
    ctx = _ctx(FACEBOOK_SHARE_URL)
    await CompileSourceStep().run(ctx)

    assert fetched == [FACEBOOK_SHARE_URL]
    assert read_videos == [FACEBOOK_REEL_URL]
    assert ctx.compiled_source is not None
    assert "mix flour and water" in ctx.compiled_source.content
    assert ctx.input.url == FACEBOOK_SHARE_URL


@pytest.mark.asyncio
async def test_a_video_site_is_read_without_fetching_its_page(read_videos: list[str], fetched: list[str]):
    ctx = _ctx(YOUTUBE_URL)
    await CompileSourceStep().run(ctx)

    assert fetched == []
    assert read_videos == [YOUTUBE_URL]
    assert ctx.compiled_source is not None
    assert "mix flour and water" in ctx.compiled_source.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        exceptions.VideoDownloadError("Failed to read video: Private video"),
        NoRecipeDataError("recipe.import-errors.video-has-no-captions"),
    ],
)
async def test_a_video_site_that_cannot_be_read_reports_why(
    monkeypatch: pytest.MonkeyPatch, fetched: list[str], error: Exception
):
    """Its page carries no more than a title, so falling back to it would only hide what went wrong."""

    def mock_read_video(url: str) -> VideoInfo:
        raise error

    monkeypatch.setattr(transcription, "read_video", mock_read_video)

    with pytest.raises(type(error)):
        await CompileSourceStep().run(_ctx(YOUTUBE_URL))

    assert fetched == []


@pytest.mark.asyncio
async def test_a_recipe_page_is_read_before_its_video(monkeypatch: pytest.MonkeyPatch, read_videos: list[str]):
    """yt-dlp knows NYT Cooking, but its pages publish the recipe their videos only demonstrate."""

    recipe = json.dumps({"@type": "Recipe", "name": "Chocolate Chip Cookies", "recipeIngredient": ["2 cups flour"]})

    async def mock_resilient_fetch(url: str) -> FetchResult:
        return html_fetch_result(f'<script type="application/ld+json">{recipe}</script>', url)

    monkeypatch.setattr(compile_source_module, "resilient_fetch", mock_resilient_fetch)

    ctx = _ctx(NYT_COOKING_URL)
    await CompileSourceStep().run(ctx)

    assert read_videos == []
    assert ctx.compiled_source is not None
    assert "2 cups flour" in ctx.compiled_source.content


@pytest.mark.asyncio
async def test_a_page_without_a_recipe_falls_back_to_its_video(monkeypatch: pytest.MonkeyPatch, read_videos: list[str]):
    async def mock_resilient_fetch(url: str) -> FetchResult:
        video = json.dumps({"@type": "VideoObject", "name": "Chocolate Chip Cookie Recipe"})
        return html_fetch_result(f'<script type="application/ld+json">{video}</script>', url)

    monkeypatch.setattr(compile_source_module, "resilient_fetch", mock_resilient_fetch)

    ctx = _ctx(NYT_COOKING_URL)
    await CompileSourceStep().run(ctx)

    assert read_videos == [NYT_COOKING_URL]
    assert ctx.compiled_source is not None
    assert "mix flour and water" in ctx.compiled_source.content


class RateLimitedCompiler(SourceCompiler):
    source_type = SourceType.CONTENT

    def can_compile(self) -> bool:
        return True

    async def compile(self) -> OpenAICompiledSource | None:
        raise exceptions.RateLimitError("You've hit your usage limit")


class UnreachableCompiler(SourceCompiler):
    source_type = SourceType.CONTENT

    def can_compile(self) -> bool:
        return True

    async def compile(self) -> OpenAICompiledSource | None:
        raise AssertionError("every other compiler would hit the same limit")


@pytest.mark.asyncio
async def test_a_usage_limit_stops_the_import():
    """It used to be swallowed like any other failure, and reported as no recipe being found."""

    ctx = _ctx("https://example.com/recipe")
    ctx.input = WorkflowInput(content="2 cups flour")

    with pytest.raises(exceptions.RateLimitError):
        await CompileSourceStep(compilers=[RateLimitedCompiler, UnreachableCompiler]).run(ctx)


class EchoContentCompiler(SourceCompiler):
    """Reads supplied content as it is, as a stand-in for the AI"""

    source_type = SourceType.CONTENT

    def can_compile(self) -> bool:
        return bool(self.content)

    async def compile(self) -> OpenAICompiledSource | None:
        return OpenAICompiledSource(contains_recipe=True, content=self.content or "")


@pytest.mark.asyncio
async def test_pasted_text_carries_a_video_that_cannot_be_read(monkeypatch: pytest.MonkeyPatch, fetched: list[str]):
    """
    When a post can't be read, the import page offers to import the recipe's text instead, keeping
    the post as its source. The post's own failure mustn't sink that.
    """

    def mock_read_video(url: str) -> VideoInfo:
        raise exceptions.VideoDownloadError("Failed to read video: Private video")

    monkeypatch.setattr(transcription, "read_video", mock_read_video)
    ctx = _ctx(YOUTUBE_URL)
    ctx.input = WorkflowInput(url=YOUTUBE_URL, content="2 cups flour, 1 cup water. Mix and bake.")

    await CompileSourceStep(compilers=[TranscriptionCompiler, EchoContentCompiler]).run(ctx)

    assert ctx.compiled_source is not None
    assert "2 cups flour" in ctx.compiled_source.content
    # nor is the post's page read instead, which holds no more than its title
    assert fetched == []
