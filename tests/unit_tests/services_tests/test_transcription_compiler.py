import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import mealie.services.recipe.import_workflow.compilers.linked_recipe as linked_recipe_module
from mealie.pkgs.safehttp.fetch import FetchResult
from mealie.services.openai import transcription
from mealie.services.openai.transcription import VideoInfo
from mealie.services.recipe.import_workflow.compilers.transcription import (
    RECOGNIZED_CAPTIONS_PREAMBLE,
    TranscriptionCompiler,
)
from mealie.services.recipe.import_workflow.context import WorkflowContext, WorkflowInput, WorkflowOptions
from mealie.services.recipe.import_workflow.exceptions import NoRecipeDataError

VIDEO_URL = "https://www.youtube.com/watch?v=abc"
CAPTIONS = "### Mixing the dough (0:00)\n\nfour hundred grams of flour and a pinch of salt"


def _ctx(*, audio_provider: bool) -> WorkflowContext:
    ai = MagicMock()
    ai.provider_settings.audio_provider_enabled = audio_provider
    ai.transcribe_audio = AsyncMock(return_value="transcribed from the audio")
    translator = MagicMock()
    translator.t.side_effect = lambda key: key
    return WorkflowContext(
        input=WorkflowInput(url=VIDEO_URL),
        options=WorkflowOptions(),
        repos=MagicMock(),
        translator=translator,
        ai=ai,
        on_progress=AsyncMock(),
    )


def _progress(ctx: WorkflowContext) -> list[str]:
    assert isinstance(ctx.on_progress, AsyncMock)
    return [call.args[0] for call in ctx.on_progress.call_args_list]


@pytest.fixture()
def video(monkeypatch: pytest.MonkeyPatch) -> VideoInfo:
    """The video yt-dlp reads, which tests adjust before compiling"""

    info = VideoInfo(
        title="Foolproof Pan Pizza",
        description="The easiest pizza you'll ever make.",
        thumbnail_url="https://i.ytimg.test/pizza.jpg",
        duration=600,
        captions=CAPTIONS,
        can_download=True,
    )
    monkeypatch.setattr(transcription, "read_video", lambda url: info)
    return info


@pytest.fixture()
def downloads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    downloaded: list[str] = []

    def mock_download_audio(url: str, temp_path: Path) -> Path:
        downloaded.append(url)
        return temp_path / "audio.mp3"

    monkeypatch.setattr(transcription, "download_audio", mock_download_audio)
    return downloaded


@pytest.mark.asyncio
async def test_captions_are_read_without_an_audio_provider(video: VideoInfo, downloads: list[str]):
    ctx = _ctx(audio_provider=False)

    compiled = await TranscriptionCompiler(ctx).compile()

    assert compiled is not None
    assert compiled.contains_recipe
    assert compiled.content == (
        "# Foolproof Pan Pizza\n\n## Video description\n\nThe easiest pizza you'll ever make.\n\n"
        f"## Video transcript\n\n{CAPTIONS}"
    )
    assert compiled.image_url == "https://i.ytimg.test/pizza.jpg"
    assert downloads == []
    ctx.ai.transcribe_audio.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_recognized_captions_come_with_a_warning_about_mishearings(video: VideoInfo):
    """Otherwise "Keep each ingredient exactly as written" keeps "dried word gone oh" too."""

    video.captions_recognized = True

    compiled = await TranscriptionCompiler(_ctx(audio_provider=False)).compile()

    assert compiled is not None
    assert compiled.content.endswith(f"## Video transcript\n\n{RECOGNIZED_CAPTIONS_PREAMBLE}\n\n{CAPTIONS}")


@pytest.mark.asyncio
async def test_captions_are_read_even_with_an_audio_provider(video: VideoInfo, downloads: list[str]):
    compiled = await TranscriptionCompiler(_ctx(audio_provider=True)).compile()

    assert compiled is not None
    assert CAPTIONS in compiled.content
    assert downloads == []


@pytest.mark.asyncio
async def test_a_video_without_captions_is_transcribed(video: VideoInfo, downloads: list[str]):
    video.captions = ""
    ctx = _ctx(audio_provider=True)

    compiled = await TranscriptionCompiler(ctx).compile()

    assert compiled is not None
    assert "## Video transcript\n\ntranscribed from the audio" in compiled.content
    assert downloads == [VIDEO_URL]
    assert _progress(ctx) == [
        "recipe.create-progress.downloading-audio",
        "recipe.create-progress.transcribing-audio-with-ai",
    ]


@pytest.mark.asyncio
async def test_a_video_without_captions_or_audio_provider_is_read_from_its_description(
    video: VideoInfo, downloads: list[str]
):
    video.captions = ""

    compiled = await TranscriptionCompiler(_ctx(audio_provider=False)).compile()

    assert compiled is not None
    assert compiled.content == "# Foolproof Pan Pizza\n\n## Video description\n\nThe easiest pizza you'll ever make."
    assert downloads == []


@pytest.mark.asyncio
async def test_a_video_too_long_to_transcribe_is_read_from_its_description(video: VideoInfo, downloads: list[str]):
    video.captions = ""
    video.duration = transcription.MAX_TRANSCRIBED_SECONDS + 1

    compiled = await TranscriptionCompiler(_ctx(audio_provider=True)).compile()

    assert compiled is not None
    assert "## Video transcript" not in compiled.content
    assert downloads == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("audio_provider", "expected_key"),
    [
        (False, "recipe.import-errors.video-has-no-captions"),
        (True, "recipe.import-errors.no-recipe-found"),
    ],
)
async def test_a_video_with_nothing_to_read(
    video: VideoInfo, downloads: list[str], audio_provider: bool, expected_key: str
):
    video.captions = ""
    video.description = "  "
    video.duration = transcription.MAX_TRANSCRIBED_SECONDS + 1

    with pytest.raises(NoRecipeDataError, match=expected_key):
        await TranscriptionCompiler(_ctx(audio_provider=audio_provider)).compile()


@pytest.mark.asyncio
async def test_a_page_with_no_video_is_left_to_be_read_as_a_webpage(video: VideoInfo, downloads: list[str]):
    """yt-dlp knows NYT Cooking, for one, but most of its recipes have no video."""

    video.captions = ""
    video.can_download = False

    assert await TranscriptionCompiler(_ctx(audio_provider=True)).compile() is None
    assert downloads == []


def _recipe_page(recipe: dict) -> str:
    return f'<html><head><script type="application/ld+json">{json.dumps(recipe)}</script></head></html>'


@pytest.mark.asyncio
async def test_the_written_recipe_the_description_links_to_is_read_too(
    video: VideoInfo, monkeypatch: pytest.MonkeyPatch
):
    video.description = "Full recipe: http://pizza.test/pan-pizza"
    fetched: list[str] = []

    async def mock_resilient_fetch(url: str) -> FetchResult:
        fetched.append(url)
        page = _recipe_page(
            {
                "@type": "Recipe",
                "name": "Foolproof Pan Pizza",
                "image": "https://pizza.test/pan-pizza.jpg",
                "recipeIngredient": ["400g bread flour"],
            }
        )
        return FetchResult(page.encode(), 200, "https://pizza.test/pan-pizza", httpx.Headers(), "utf-8")

    monkeypatch.setattr(linked_recipe_module, "resilient_fetch", mock_resilient_fetch)
    ctx = _ctx(audio_provider=False)

    compiled = await TranscriptionCompiler(ctx).compile()

    assert fetched == ["http://pizza.test/pan-pizza"]
    assert compiled is not None
    written = compiled.content.split("## Written recipe\n\n")[1].split("## Video transcript")[0]
    assert "https://pizza.test/pan-pizza" in written
    assert "400g bread flour" in written
    assert compiled.content.endswith(f"## Video transcript\n\n{CAPTIONS}")
    # the dish's own photo beats a thumbnail
    assert compiled.image_url == "https://pizza.test/pan-pizza.jpg"
    assert _progress(ctx) == ["recipe.create-progress.reading-linked-recipe"]


@pytest.mark.asyncio
async def test_a_written_recipe_that_cannot_be_read_is_left_out(video: VideoInfo, monkeypatch: pytest.MonkeyPatch):
    video.description = "Full recipe: https://pizza.test/pan-pizza"

    async def mock_resilient_fetch(url: str) -> FetchResult:
        raise RuntimeError("could not resolve host: pizza.test")

    monkeypatch.setattr(linked_recipe_module, "resilient_fetch", mock_resilient_fetch)

    compiled = await TranscriptionCompiler(_ctx(audio_provider=False)).compile()

    assert compiled is not None
    assert "## Written recipe" not in compiled.content
    assert compiled.image_url == "https://i.ytimg.test/pizza.jpg"
