"""
Reads recipe videos with yt-dlp.

A video is read from what it publishes about itself, without downloading it: its title, its
description, its chapters, and its captions. Only a video with no captions has its audio
downloaded, and only so that an audio provider can transcribe it.
"""

import functools
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mealie.core import exceptions
from mealie.core.config import get_app_settings
from mealie.core.root_logger import get_logger

from .openai import OpenAIService

logger = get_logger()

VIDEO_SITES = {"youtube", "vimeo", "tiktok", "instagram", "facebook", "dailymotion"}
"""
yt-dlp extractors for sites where the video is the whole post. Their pages carry little more than
the video's title, and never a recipe as structured data, so there's no point fetching them.
"""

CAPTION_FORMATS = ("vtt", "srt")
"""Caption formats `parse_captions` can read, in order of preference"""

MAX_TRANSCRIBED_SECONDS = 90 * 60
"""
Longest video whose audio is sent to the audio provider. Providers cap uploads by size, and
OpenAI's 25 MB cap is reached by an hour and three quarters of the 32 kbps audio sent to them.
"""

CUE_TIMING = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,]\d+\s*-->")
MARKUP = re.compile(r"<[^>]*>")
SOUND_CUE = re.compile(r"\[[^\]]*\]|\([^)]*\)|[♪\s]+")
"""A caption line that only describes a sound, such as "[Music]" or "(sizzling)" """


@dataclass
class Chapter:
    start: float
    """Seconds from the start of the video"""

    title: str


@dataclass
class CaptionTrack:
    language: str
    url: str
    automatic: bool
    """Whether the captions were recognized from the speech, rather than written by the creator"""


@dataclass
class VideoInfo:
    """What a video says about itself, read without downloading it."""

    title: str = ""
    description: str = ""
    thumbnail_url: str | None = None
    duration: float | None = None
    chapters: list[Chapter] = field(default_factory=list)

    captions: str = ""
    """The video's captions as plain text, with a heading for each chapter, or empty if it has none"""

    captions_recognized: bool = False
    """Whether the captions were recognized from the speech, which leaves them unpunctuated and misheard in places"""

    can_download: bool = False
    """
    Whether there's anything to download. A few sites yt-dlp knows have pages with no video on
    them, and a live stream can't be downloaded until it's over.
    """


@functools.cache
def get_yt_dlp_extractors() -> list:
    """Build and cache the yt-dlp extractor list once per process lifetime."""
    import yt_dlp
    from yt_dlp.extractor.generic import GenericIE

    return [ie for ie in yt_dlp.extractor.gen_extractors() if ie.working() and not isinstance(ie, GenericIE)]


@functools.lru_cache(maxsize=256)
def get_extractor_name(url: str) -> str | None:
    """The name of the yt-dlp extractor that would read the URL, or None if none would."""

    if not url:
        return None

    return next((ie.IE_NAME for ie in get_yt_dlp_extractors() if ie.suitable(url)), None)


def is_video_url(url: str) -> bool:
    """Whether yt-dlp recognizes the URL as something it can download."""

    return get_extractor_name(url) is not None


def is_video_site(url: str) -> bool:
    """Whether the URL is on one of the `VIDEO_SITES`, where the video is the whole post."""

    name = get_extractor_name(url)
    return name is not None and name.split(":")[0].lower() in VIDEO_SITES


def _ydl_options(**options: Any) -> dict[str, Any]:
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "noplaylist": True,
        # a playlist or channel URL would otherwise have every one of its videos read
        "extract_flat": "in_playlist",
        **options,
    }

    settings = get_app_settings()
    if settings.YTDLP_COOKIEFILE:
        ydl_opts["cookiefile"] = settings.YTDLP_COOKIEFILE

    return ydl_opts


def read_video(url: str) -> VideoInfo:
    """
    Reads a video's title, description, chapters, and captions, without downloading the video.

    Raises `VideoDownloadError` if yt-dlp can't read the video at all.
    """

    import yt_dlp

    # a video whose formats can't be read, after a site change yt-dlp hasn't caught up with say,
    # usually still has its captions, and those are all that's needed here
    ydl_opts = _ydl_options(skip_download=True, ignore_no_formats_error=True)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise exceptions.VideoDownloadError("yt-dlp couldn't read the video")
            if "entries" in info:
                raise exceptions.VideoDownloadError("The URL is for a playlist or channel, not a video")

            chapters = [
                Chapter(start=float(chapter.get("start_time") or 0), title=chapter["title"])
                for chapter in info.get("chapters") or []
                if chapter.get("title")
            ]

            captions = ""
            track = pick_caption_track(info)
            if track:
                try:
                    with ydl.urlopen(track.url) as response:
                        captions = parse_captions(response.read().decode("utf-8", errors="replace"), chapters)
                except Exception:
                    logger.exception(f"Failed to download the video's {track.language} captions")
    except exceptions.VideoDownloadError:
        raise
    except Exception as e:
        raise exceptions.VideoDownloadError(f"Failed to read video: {e}") from e

    return VideoInfo(
        title=info.get("title") or "",
        description=info.get("description") or "",
        thumbnail_url=info.get("thumbnail") or None,
        duration=info.get("duration"),
        chapters=chapters,
        captions=captions,
        captions_recognized=bool(captions and track and track.automatic),
        can_download=bool(info.get("formats")) and info.get("live_status") not in ("is_live", "is_upcoming"),
    )


def pick_caption_track(info: dict[str, Any]) -> CaptionTrack | None:
    """
    Picks the captions that best record what a video says, from its yt-dlp info.

    Captions the creator wrote in the language the video is spoken in come first, then captions
    recognized from the speech. YouTube also offers its recognized captions machine translated
    into a hundred-odd languages, marking the original track with "-orig". Translations are never
    used: the import translates the recipe itself, if asked, and does a better job of it.
    """

    language = (info.get("language") or "").casefold()
    base_language = language.split("-")[0]

    def readable(tracks: dict[str, list[dict[str, Any]]] | None) -> dict[str, str]:
        """Each language's caption URL, in the best format `parse_captions` can read"""

        urls: dict[str, str] = {}
        for track_language, formats in (tracks or {}).items():
            if track_language == "live_chat":
                continue

            by_format = {fmt.get("ext"): fmt.get("url") for fmt in formats or [] if fmt.get("url")}
            if url := next((by_format[ext] for ext in CAPTION_FORMATS if by_format.get(ext)), None):
                urls[track_language] = url

        return urls

    def is_spoken(track_language: str) -> bool:
        track_language = track_language.casefold()
        return bool(base_language) and (track_language == language or track_language.split("-")[0] == base_language)

    written = readable(info.get("subtitles"))
    recognized = readable(info.get("automatic_captions"))

    candidates = [
        *(CaptionTrack(lang, url, False) for lang, url in written.items() if is_spoken(lang)),
        *(CaptionTrack(lang, url, True) for lang, url in recognized.items() if lang.endswith("-orig")),
        *(CaptionTrack(lang, url, True) for lang, url in recognized.items() if is_spoken(lang)),
        # captions the creator wrote in another language are still a faithful record of the video
        *(CaptionTrack(lang, url, False) for lang, url in written.items()),
    ]

    # without knowing the video's language, there's no telling recognized captions from their
    # translations, except on YouTube, whose original track was already picked out above
    if not base_language and len(recognized) == 1:
        candidates += [CaptionTrack(lang, url, True) for lang, url in recognized.items()]

    return candidates[0] if candidates else None


def parse_captions(content: str, chapters: list[Chapter] | None = None) -> str:
    """
    Turns WebVTT or SRT captions into plain text, with a heading where each chapter starts.

    YouTube's recognized captions scroll: each cue repeats the line before it, so every line would
    otherwise appear two or three times over. Repeated lines are dropped, as are lines that only
    describe a sound, like "[Music]".
    """

    upcoming = sorted(chapters or [], key=lambda chapter: chapter.start)
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    previous: str | None = None
    in_cue = False

    for line in content.splitlines():
        if timing := CUE_TIMING.search(line):
            in_cue = True
            start = int(timing[1] or 0) * 3600 + int(timing[2]) * 60 + int(timing[3])
            while upcoming and upcoming[0].start <= start:
                chapter = upcoming.pop(0)
                sections.append((f"{chapter.title} ({_timestamp(chapter.start)})", []))
            continue

        # a blank line ends a cue, but YouTube pads cues with lines holding a single space
        if not line:
            in_cue = False
            continue

        # outside a cue are headers, NOTE and STYLE blocks, and SRT's cue numbers
        if not in_cue:
            continue

        text = " ".join(html.unescape(MARKUP.sub("", line)).split())
        if not text or text == previous or SOUND_CUE.fullmatch(text):
            continue

        sections[-1][1].append(text)
        previous = text

    return "\n\n".join(
        (f"### {heading}\n\n" if heading else "") + " ".join(lines) for heading, lines in sections if lines
    )


def _timestamp(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def download_audio(url: str, temp_path: Path) -> Path:
    """Downloads a video's audio as low bitrate mono MP3, which is all a transcription needs."""

    import yt_dlp

    output = temp_path / "audio"
    ydl_opts = _ydl_options(
        format="bestaudio/best",
        outtmpl=f"{output}.%(ext)s",
        postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "32"}],
        postprocessor_args=["-ac", "1"],
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as e:
        raise exceptions.VideoDownloadError(f"Failed to download the video's audio: {e}") from e

    audio = output.with_suffix(".mp3")
    if not audio.exists():
        raise exceptions.VideoDownloadError("yt-dlp didn't save the video's audio")

    return audio


async def transcribe_audio(audio: Path, openai_service: OpenAIService) -> str:
    """Transcribes audio with the group's audio provider."""

    try:
        transcript = await openai_service.transcribe_audio(audio)
    except exceptions.RateLimitError:
        raise
    except Exception as e:
        raise exceptions.OpenAIServiceError(f"Failed to transcribe audio: {e}") from e

    if not transcript:
        raise exceptions.OpenAIServiceError("No transcription returned from OpenAI")

    return transcript
