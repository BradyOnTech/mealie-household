import asyncio

from mealie.core.dependencies.dependencies import get_temporary_path
from mealie.schema.openai.compiled_source import OpenAICompiledSource
from mealie.services.openai import transcription
from mealie.services.openai.transcription import VideoInfo

from ..exceptions import NoRecipeDataError
from .base import SourceCompiler, SourceType
from .linked_recipe import LinkedRecipe, find_linked_recipe, recipe_links

WRITTEN_RECIPE_PREAMBLE = (
    "The video's description links to a written version of its recipe, reproduced below from {url}. "
    "It's the same recipe as the video's, so take its ingredients and steps as written, and use the "
    "transcript for tips and for anything the written recipe leaves out."
)

RECOGNIZED_CAPTIONS_PREAMBLE = (
    "These captions were recognized automatically from the video's speech, so they're unpunctuated "
    "and some words are misheard. Write each ingredient and step the way the cook meant it, rather than "
    'copying a mishearing ("dried oregano", not "dried word gone oh"), and write spoken amounts the '
    'way a recipe would ("2 cups (280 g) flour", not "about two cups of flour which is about 280 grams").'
)


class TranscriptionCompiler(SourceCompiler):
    """
    Compiles a video from what it says about itself: its title, its description, and its captions,
    along with the written recipe its description links to, if there is one. Only a video with no
    captions has its audio downloaded, and only if there's an audio provider to transcribe it.

    Each of these is already a faithful record of the source, so no further AI call is made.
    """

    source_type = SourceType.URL
    progress_key = "recipe.create-progress.reading-video"

    def _url(self) -> str | None:
        return self.ctx.resolved_url or self.ctx.input.url

    def can_compile(self) -> bool:
        return transcription.is_video_url(self._url() or "")

    async def compile(self) -> OpenAICompiledSource | None:
        url = self._url() or ""
        video = await asyncio.to_thread(transcription.read_video, url)

        if not (video.captions or video.can_download):
            # yt-dlp knows the site, but there's no video on this page (most NYT Cooking recipes,
            # for one), so leave it to be read as a webpage
            return None

        transcript = video.captions or await self._transcribe(url, video)
        linked = await self._find_linked_recipe(video)

        if not (transcript or linked or video.description.strip()):
            raise NoRecipeDataError(self._nothing_to_read())

        return OpenAICompiledSource(
            contains_recipe=True,
            content=self._document(video, transcript, linked, recognized=video.captions_recognized),
            language=None,
            # a written recipe's photo is of the dish, where a thumbnail is often a face and a caption
            image_url=(linked.image_url if linked else None) or video.thumbnail_url,
        )

    def _audio_provider_enabled(self) -> bool:
        settings = self.ctx.ai.provider_settings
        return bool(settings and settings.audio_provider_enabled)

    async def _transcribe(self, url: str, video: VideoInfo) -> str:
        """Transcribes a video that has no captions, when there's an audio provider to do it."""

        if not (video.can_download and self._audio_provider_enabled()):
            return ""

        if video.duration and video.duration > transcription.MAX_TRANSCRIBED_SECONDS:
            self.logger.info(f"Not transcribing a {video.duration:.0f} second video, which is too long")
            return ""

        with get_temporary_path() as temp_path:
            await self.ctx.report_progress("recipe.create-progress.downloading-audio")
            audio = await asyncio.to_thread(transcription.download_audio, url, temp_path)

            await self.ctx.report_progress("recipe.create-progress.transcribing-audio-with-ai")
            return await transcription.transcribe_audio(audio, self.ctx.ai)

    async def _find_linked_recipe(self, video: VideoInfo) -> LinkedRecipe | None:
        links = recipe_links(video.description)
        if not links:
            return None

        await self.ctx.report_progress("recipe.create-progress.reading-linked-recipe")
        try:
            return await find_linked_recipe(video.title, links)
        except Exception:
            # the written recipe is a bonus, so the video is still imported without it
            self.logger.exception("Failed to read the recipe linked from the video")
            return None

    def _nothing_to_read(self) -> str:
        if self._audio_provider_enabled():
            return self.ctx.translator.t("recipe.import-errors.no-recipe-found")

        return self.ctx.translator.t("recipe.import-errors.video-has-no-captions")

    @staticmethod
    def _document(video: VideoInfo, transcript: str, linked: LinkedRecipe | None, *, recognized: bool) -> str:
        """
        Puts the parts together, `recognized` saying whether the transcript is captions that were
        recognized from the video's speech
        """

        parts = [f"# {video.title}"] if video.title else []
        if description := video.description.strip():
            parts.append(f"## Video description\n\n{description}")
        if linked:
            parts.append(f"## Written recipe\n\n{WRITTEN_RECIPE_PREAMBLE.format(url=linked.url)}\n\n{linked.content}")
        if transcript:
            preamble = f"{RECOGNIZED_CAPTIONS_PREAMBLE}\n\n" if recognized else ""
            parts.append(f"## Video transcript\n\n{preamble}{transcript}")

        return "\n\n".join(parts)
