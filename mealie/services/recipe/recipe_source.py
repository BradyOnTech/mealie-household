from urllib.parse import urlsplit


def instagram_source_url(url: str | None) -> str | None:
    """Recognize real Instagram source links without matching lookalike domains."""
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return url.strip()
    return None
