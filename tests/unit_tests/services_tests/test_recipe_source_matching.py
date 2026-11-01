import pytest

from mealie.services.recipe.recipe_source_matching import source_key, source_search_term


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://youtu.be/abc123?si=share", "youtube:abc123"),
        ("https://www.youtube.com/watch?v=abc123&t=30", "youtube:abc123"),
        ("https://m.youtube.com/shorts/abc123", "youtube:abc123"),
        ("https://www.instagram.com/reel/C0de/?igsh=xyz", "instagram:C0de"),
        ("https://instagram.com/chef/p/C0de", "instagram:C0de"),
        ("https://www.instagram.com/p/DS66ymegPwK/?srtk=MWplbm9wN3ZrMWFqNw==", "instagram:DS66ymegPwK"),
        ("https://www.tiktok.com/@chef/video/42?is_from_webapp=1", "tiktok:42"),
        ("https://www.example.test/chili/?utm_source=x&fbclid=y", "example.test/chili"),
        ("http://example.test/chili", "example.test/chili"),
        ("https://example.test/recipe.php?ref=home&id=12", "example.test/recipe.php?id=12"),
        ("https://Example.TEST/Chili", "example.test/Chili"),
    ],
)
def test_source_key(url: str, expected: str):
    assert source_key(url) == expected


def test_source_key_keeps_meaningful_query_parameters():
    assert source_key("https://example.test/recipe.php?id=13") != source_key("https://example.test/recipe.php?id=12")


@pytest.mark.parametrize("url", [None, "", "not a link", "ftp://example.test/chili", "mailto:chef@example.test"])
def test_source_key_ignores_non_links(url: str | None):
    assert source_key(url) is None


@pytest.mark.parametrize(
    "key, expected",
    [
        ("youtube:abc123", "abc123"),
        ("example.test/chili", "example.test/chili"),
        ("example.test/recipe.php?id=12", "example.test/recipe.php"),
        ("example.test:8080/chili", "example.test:8080/chili"),
        ("youtube:ab", None),
    ],
)
def test_source_search_term(key: str, expected: str | None):
    assert source_search_term(key) == expected
