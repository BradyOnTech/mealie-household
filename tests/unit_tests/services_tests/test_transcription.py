import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

import mealie.services.openai.transcription as transcription_module
from mealie.core import exceptions
from mealie.services.openai import transcription
from mealie.services.openai.transcription import CaptionTrack, Chapter
from mealie.services.recipe.import_workflow.compilers.linked_recipe import names_match
from mealie.services.recipe.import_workflow.compilers.transcription import TranscriptionCompiler

# YouTube's recognized captions, as yt-dlp downloads them: each cue repeats the line before it,
# a near-instant cue in between holds the finished line, and padding lines hold a single space
YOUTUBE_CAPTIONS = """WEBVTT
Kind: captions
Language: en

00:00:00.240 --> 00:00:02.950 align:start position:0%

everyone<00:00:00.480><c> it's</c><00:00:00.640><c> Kenji</c>

00:00:02.950 --> 00:00:02.960 align:start position:0%
everyone it's Kenji


00:00:02.960 --> 00:00:05.150 align:start position:0%
everyone it's Kenji
I'm<00:00:03.199><c> making</c><00:00:03.360><c> pizza</c>

00:00:05.150 --> 00:00:05.160 align:start position:0%
I'm making pizza


00:01:05.160 --> 00:01:07.000 align:start position:0%
I'm making pizza
[Music]

00:01:07.000 --> 00:01:09.000 align:start position:0%
[Music]
add<00:01:07.300><c> the</c><00:01:07.500><c> sauce</c>
"""


def test_parse_captions_drops_the_lines_youtube_repeats():
    assert transcription.parse_captions(YOUTUBE_CAPTIONS) == "everyone it's Kenji I'm making pizza add the sauce"


def test_parse_captions_adds_a_heading_where_each_chapter_starts():
    chapters = [Chapter(start=60, title="Making the sauce"), Chapter(start=0, title="Mixing the dough")]

    assert transcription.parse_captions(YOUTUBE_CAPTIONS, chapters) == (
        "### Mixing the dough (0:00)\n\neveryone it's Kenji I'm making pizza"
        "\n\n### Making the sauce (1:00)\n\nadd the sauce"
    )


def test_parse_captions_reads_srt():
    captions = (
        "1\n00:00:01,000 --> 00:00:03,000\nPreheat the oven to 220&deg;C.\n\n"
        "2\n00:00:03,500 --> 00:00:05,000\n<i>Then</i> mix the flour &amp; water.\n\n"
        "3\n01:02:03,000 --> 01:02:04,000\n(sizzling)\n"
    )

    assert transcription.parse_captions(captions) == "Preheat the oven to 220°C. Then mix the flour & water."


def test_parse_captions_skips_everything_outside_cues():
    captions = (
        "WEBVTT\n\nSTYLE\n::cue { color: red }\n\nNOTE written by hand\n\n"
        "intro\n00:01.000 --> 00:02.000\nAdd [a pinch of] salt\n♪ ♪\n\n"
        "00:02.000 --> 00:03.000\nand stir\n"
    )

    assert transcription.parse_captions(captions) == "Add [a pinch of] salt and stir"


def test_parse_captions_formats_long_chapter_times():
    captions = "00:00.000 --> 00:01.000\nfirst\n\n1:01:01.000 --> 1:01:02.000\nlast\n"

    parsed = transcription.parse_captions(captions, [Chapter(start=3661, title="The end")])

    assert parsed == "first\n\n### The end (1:01:01)\n\nlast"


def _formats(language: str, *exts: str) -> list[dict[str, str]]:
    return [{"ext": ext, "url": f"https://captions.test/{language}.{ext}"} for ext in exts]


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        pytest.param(
            {
                "language": "en-US",
                "automatic_captions": {
                    "fr": _formats("fr", "vtt"),
                    "en": _formats("en", "vtt"),
                    "en-orig": _formats("en-orig", "json3", "srt", "vtt"),
                },
            },
            CaptionTrack("en-orig", "https://captions.test/en-orig.vtt", True),
            id="youtube's original recognized track over its translations",
        ),
        pytest.param(
            {
                "language": "en",
                "subtitles": {"en-GB": _formats("en-GB", "srt")},
                "automatic_captions": {"en-orig": _formats("en-orig", "vtt")},
            },
            CaptionTrack("en-GB", "https://captions.test/en-GB.srt", False),
            id="the creator's own captions in the spoken language",
        ),
        pytest.param(
            {
                "language": "es",
                "subtitles": {"en": _formats("en", "vtt")},
                "automatic_captions": {"es-orig": _formats("es-orig", "vtt"), "en": _formats("en", "vtt")},
            },
            CaptionTrack("es-orig", "https://captions.test/es-orig.vtt", True),
            id="the spoken language over a translation the creator wrote",
        ),
        pytest.param(
            {"language": "de", "subtitles": {"en": _formats("en", "vtt")}},
            CaptionTrack("en", "https://captions.test/en.vtt", False),
            id="a translation the creator wrote over nothing",
        ),
        pytest.param(
            {"automatic_captions": {"eng-US": _formats("eng-US", "vtt")}},
            CaptionTrack("eng-US", "https://captions.test/eng-US.vtt", True),
            id="the only recognized track of a video in an unknown language",
        ),
        pytest.param(
            {"automatic_captions": {"de": _formats("de", "vtt"), "fr": _formats("fr", "vtt")}},
            None,
            id="no way to tell recognized captions from translations",
        ),
        pytest.param(
            {"language": "en", "subtitles": {"live_chat": _formats("live_chat", "vtt")}},
            None,
            id="live chat replays aren't captions",
        ),
        pytest.param(
            {"language": "en", "automatic_captions": {"en-orig": _formats("en-orig", "json3", "ttml")}},
            None,
            id="only formats that can't be read",
        ),
        pytest.param({"language": "en"}, None, id="no captions at all"),
    ],
)
def test_pick_caption_track(info: dict[str, Any], expected: CaptionTrack | None):
    assert transcription.pick_caption_track(info) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://www.facebook.com/reel/1433866715330175/", True),
        ("https://www.facebook.com/share/r/1DWziuVHRi/", False),
        ("https://cooking.nytimes.com/recipes/1015819-chocolate-chip-cookies", True),
        ("https://example.com/recipe", False),
        ("", False),
    ],
)
def test_is_video_url(url: str, expected: bool):
    """
    yt-dlp's Facebook extractor matches /reel/ but not /share/r/ share links.
    Those are handled by following redirects in the import workflow.
    """

    assert transcription.is_video_url(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://youtu.be/dQw4w9WgXcQ", True),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", True),
        ("https://vimeo.com/123456789", True),
        ("https://www.tiktok.com/@chef/video/7300000000000000000", True),
        ("https://www.facebook.com/reel/1433866715330175/", True),
        # yt-dlp knows these recipe sites, but their pages publish the recipe itself
        ("https://cooking.nytimes.com/recipes/1015819-chocolate-chip-cookies", False),
        ("https://www.bbc.co.uk/food/recipes/easy_chocolate_cake_31070", False),
        ("https://www.facebook.com/share/r/1DWziuVHRi/", False),
        ("https://example.com/recipe", False),
        ("", False),
    ],
)
def test_is_video_site(url: str, expected: bool):
    assert transcription.is_video_site(url) is expected


def test_transcription_compiler_uses_resolved_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        transcription,
        "is_video_url",
        lambda url: url == "https://www.facebook.com/reel/1433866715330175/",
    )

    ctx = Mock()
    ctx.input.url = "https://www.facebook.com/share/r/1DWziuVHRi/"
    ctx.resolved_url = "https://www.facebook.com/reel/1433866715330175/"

    compiler = TranscriptionCompiler(ctx)
    assert compiler.can_compile() is True
    assert compiler._url() == ctx.resolved_url


class _SettingsStub:
    YTDLP_COOKIEFILE: str | None = None


@pytest.fixture()
def settings_stub(monkeypatch: pytest.MonkeyPatch):
    s = _SettingsStub()
    monkeypatch.setattr(transcription_module, "get_app_settings", lambda: s)
    return s


VIDEO_INFO: dict[str, Any] = {
    "title": "Pan Pizza",
    "description": "Full recipe: https://example.com/pan-pizza",
    "thumbnail": "https://i.ytimg.test/pan-pizza.jpg",
    "duration": 1934,
    "language": "en",
    "formats": [{"format_id": "251"}],
    "chapters": [{"start_time": 0.0, "title": "Mixing the dough"}],
    "automatic_captions": {"en-orig": _formats("en-orig", "vtt")},
}


class _FakeYoutubeDL:
    """Stands in for yt-dlp, recording how it was used instead of hitting the network."""

    info: Any = VIDEO_INFO
    captions: dict[str, str] = {}
    last_opts: dict | None = None
    opened: list[str] = []
    saves_audio = True

    def __init__(self, opts: dict):
        _FakeYoutubeDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url: str, download: bool = True):
        if isinstance(self.info, Exception):
            raise self.info

        if download and self.saves_audio:
            Path(self.last_opts["outtmpl"].replace("%(ext)s", "mp3")).write_bytes(b"mp3")  # type: ignore[index]

        return self.info

    def urlopen(self, url: str):
        _FakeYoutubeDL.opened.append(url)
        if url not in self.captions:
            raise OSError("HTTP Error 429: Too Many Requests")

        return io.BytesIO(self.captions[url].encode())


@pytest.fixture()
def fake_yt_dlp(monkeypatch: pytest.MonkeyPatch, settings_stub: _SettingsStub):
    _FakeYoutubeDL.info = VIDEO_INFO
    _FakeYoutubeDL.captions = {"https://captions.test/en-orig.vtt": YOUTUBE_CAPTIONS}
    _FakeYoutubeDL.last_opts = None
    _FakeYoutubeDL.opened = []
    _FakeYoutubeDL.saves_audio = True
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYoutubeDL)
    return _FakeYoutubeDL


def test_read_video_reads_captions_without_downloading(fake_yt_dlp: type[_FakeYoutubeDL]):
    video = transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert fake_yt_dlp.last_opts is not None
    assert fake_yt_dlp.last_opts["skip_download"] is True
    assert fake_yt_dlp.last_opts["ignore_no_formats_error"] is True
    assert fake_yt_dlp.opened == ["https://captions.test/en-orig.vtt"]

    assert video.title == "Pan Pizza"
    assert video.description == "Full recipe: https://example.com/pan-pizza"
    assert video.thumbnail_url == "https://i.ytimg.test/pan-pizza.jpg"
    assert video.duration == 1934
    assert video.chapters == [Chapter(start=0.0, title="Mixing the dough")]
    assert video.captions.startswith("### Mixing the dough (0:00)\n\neveryone it's Kenji I'm making pizza")
    assert video.captions_recognized is True
    assert video.can_download is True


def test_read_video_knows_captions_the_creator_wrote(fake_yt_dlp: type[_FakeYoutubeDL]):
    fake_yt_dlp.info = {**VIDEO_INFO, "subtitles": {"en": _formats("en", "vtt")}}
    fake_yt_dlp.captions = {"https://captions.test/en.vtt": YOUTUBE_CAPTIONS}

    video = transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert fake_yt_dlp.opened == ["https://captions.test/en.vtt"]
    assert video.captions
    assert video.captions_recognized is False


def test_read_video_without_captions(fake_yt_dlp: type[_FakeYoutubeDL]):
    fake_yt_dlp.info = {**VIDEO_INFO, "automatic_captions": {}}

    video = transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert fake_yt_dlp.opened == []
    assert video.captions == ""
    assert video.title == "Pan Pizza"


def test_read_video_carries_on_when_the_captions_fail_to_download(fake_yt_dlp: type[_FakeYoutubeDL]):
    fake_yt_dlp.captions = {}

    video = transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert video.captions == ""
    assert video.captions_recognized is False
    assert video.description == "Full recipe: https://example.com/pan-pizza"


@pytest.mark.parametrize(
    ("info", "can_download"),
    [
        ({**VIDEO_INFO, "live_status": "is_live"}, False),
        ({**VIDEO_INFO, "live_status": "is_upcoming"}, False),
        ({**VIDEO_INFO, "live_status": "was_live"}, True),
        ({**VIDEO_INFO, "formats": []}, False),
    ],
)
def test_read_video_knows_when_there_is_nothing_to_download(
    fake_yt_dlp: type[_FakeYoutubeDL], info: dict[str, Any], can_download: bool
):
    fake_yt_dlp.info = info

    assert transcription.read_video("https://www.youtube.com/watch?v=abc").can_download is can_download


@pytest.mark.parametrize(
    "info",
    [
        pytest.param(None, id="nothing returned"),
        pytest.param({"_type": "playlist", "entries": [{"url": "https://youtu.be/abc"}]}, id="a playlist"),
        pytest.param(Exception("ERROR: [youtube] abc: Video unavailable"), id="an extraction error"),
    ],
)
def test_read_video_raises_when_there_is_no_video(fake_yt_dlp: type[_FakeYoutubeDL], info: Any):
    fake_yt_dlp.info = info

    with pytest.raises(exceptions.VideoDownloadError):
        transcription.read_video("https://www.youtube.com/watch?v=abc")


def test_read_video_omits_cookiefile_by_default(fake_yt_dlp: type[_FakeYoutubeDL]):
    transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert fake_yt_dlp.last_opts is not None
    assert "cookiefile" not in fake_yt_dlp.last_opts


def test_read_video_passes_configured_cookiefile(fake_yt_dlp: type[_FakeYoutubeDL], settings_stub: _SettingsStub):
    settings_stub.YTDLP_COOKIEFILE = "/data/cookies.txt"

    transcription.read_video("https://www.youtube.com/watch?v=abc")

    assert fake_yt_dlp.last_opts is not None
    assert fake_yt_dlp.last_opts["cookiefile"] == "/data/cookies.txt"


def test_download_audio(fake_yt_dlp: type[_FakeYoutubeDL], settings_stub: _SettingsStub, tmp_path: Path):
    settings_stub.YTDLP_COOKIEFILE = "/data/cookies.txt"

    audio = transcription.download_audio("https://www.youtube.com/watch?v=abc", tmp_path)

    assert audio == tmp_path / "audio.mp3"
    assert audio.read_bytes() == b"mp3"
    assert fake_yt_dlp.last_opts is not None
    assert fake_yt_dlp.last_opts["cookiefile"] == "/data/cookies.txt"
    assert fake_yt_dlp.last_opts["format"] == "bestaudio/best"


def test_download_audio_raises_when_nothing_is_saved(fake_yt_dlp: type[_FakeYoutubeDL], tmp_path: Path):
    fake_yt_dlp.saves_audio = False

    with pytest.raises(exceptions.VideoDownloadError):
        transcription.download_audio("https://www.youtube.com/watch?v=abc", tmp_path)


def test_download_audio_raises_on_download_errors(fake_yt_dlp: type[_FakeYoutubeDL], tmp_path: Path):
    fake_yt_dlp.info = Exception("ERROR: HTTP Error 403: Forbidden")

    with pytest.raises(exceptions.VideoDownloadError):
        transcription.download_audio("https://www.youtube.com/watch?v=abc", tmp_path)


@pytest.mark.asyncio
async def test_transcribe_audio(tmp_path: Path):
    ai = Mock()
    ai.transcribe_audio = AsyncMock(return_value="mix the flour and water")

    assert await transcription.transcribe_audio(tmp_path / "audio.mp3", ai) == "mix the flour and water"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (exceptions.RateLimitError("usage limit"), exceptions.RateLimitError),
        (RuntimeError("401 invalid_api_key"), exceptions.OpenAIServiceError),
        ("", exceptions.OpenAIServiceError),
    ],
)
async def test_transcribe_audio_errors(tmp_path: Path, result: Any, expected: type[Exception]):
    ai = Mock()
    ai.transcribe_audio = AsyncMock(side_effect=result if isinstance(result, Exception) else None)
    if not isinstance(result, Exception):
        ai.transcribe_audio.return_value = result

    with pytest.raises(expected):
        await transcription.transcribe_audio(tmp_path / "audio.mp3", ai)


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        # Instagram titles every post after its account; the caption's first line names the dish
        (
            "Video by spendpennies",
            "Roasted Cabbage Steaks turn a humble veggie\n\nRecipe: ...",
            "Roasted Cabbage Steaks turn a humble veggie",
        ),
        ("Video by pinchofnom", "#food #yum\n\nFAJITA BOMBS 💕 Get ready #fajitas", "FAJITA BOMBS 💕 Get ready"),
        ("Photo by someone", "", "Photo by someone"),
        ("Foolproof Pan Pizza", "A different first line", "Foolproof Pan Pizza"),
        ("", "Lemon Orzo", "Lemon Orzo"),
        ("Video by cook", "x" * 200, "x" * 149 + "…"),
    ],
)
def test_post_title(title: str, description: str, expected: str):
    assert transcription.post_title(title, description) == expected


def test_read_video_names_an_instagram_post_from_its_caption(fake_yt_dlp: type[_FakeYoutubeDL]):
    fake_yt_dlp.info = {
        **VIDEO_INFO,
        "title": "Video by spendpennies",
        "description": "Roasted Cabbage Steaks turn a humble veggie into a fancy side dish.\n\nRecipe below",
        "automatic_captions": {},
    }

    video = transcription.read_video("https://www.instagram.com/reel/C5bRObqqJLV/")

    assert video.title == "Roasted Cabbage Steaks turn a humble veggie into a fancy side dish."
    # so the written recipe its caption links to can be recognized as the post's
    assert names_match("Roasted Cabbage Steaks", video.title)
