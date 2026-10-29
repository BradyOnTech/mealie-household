import pytest

from mealie.services.recipe.recipe_source import instagram_source_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/video/?igsh=shared",
        "https://instagram.com/p/post/",
        "https://m.instagram.com/reel/video/",
        "https://WWW.INSTAGRAM.COM/reel/video/",
    ],
)
def test_recognizes_instagram_sources(url: str) -> None:
    assert instagram_source_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "not a URL",
        "javascript:alert(1)",
        "https://instagram.com.evil.test/reel/video/",
        "https://instagram.com@evil.test/reel/video/",
        "https://example.com/?source=instagram.com",
        "https://[broken",
        "ftp://instagram.com/reel/video/",
    ],
)
def test_rejects_unrelated_or_invalid_sources(url: str | None) -> None:
    assert instagram_source_url(url) is None
