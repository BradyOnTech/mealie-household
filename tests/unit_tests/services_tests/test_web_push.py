import json

import pytest

from mealie.services.web_push import web_push


class FakeSettings:
    def __init__(self, base_url: str, subject: str | None = None, email: str | None = None) -> None:
        self.BASE_URL = base_url
        self.WEB_PUSH_SUBJECT = subject
        self.SMTP_FROM_EMAIL = email


@pytest.mark.parametrize(
    ("base_url", "subject", "email", "expected"),
    [
        # Push services want an https URL without a port
        ("https://kitchen.example.ts.net:8445", None, None, "https://kitchen.example.ts.net"),
        ("https://kitchen.example.ts.net", "mailto:me@example.com", None, "mailto:me@example.com"),
        # Apple rejects localhost, so fall back to an email, then to the project
        ("https://localhost:9925", None, "mealie@example.com", "mailto:mealie@example.com"),
        ("http://192.168.1.20:9925", None, None, web_push.FALLBACK_SUBJECT),
        ("https://192.168.1.20", None, None, web_push.FALLBACK_SUBJECT),
    ],
)
def test_subject(monkeypatch: pytest.MonkeyPatch, base_url: str, subject: str | None, email: str | None, expected: str):
    monkeypatch.setattr(web_push, "get_app_settings", lambda: FakeSettings(base_url, subject, email))
    assert web_push.subject() == expected


def test_payload():
    message = web_push.PushMessage(title="Sam", body="Out of milk", url="/household/messages", badge=2)
    assert json.loads(message.payload()) == {
        "title": "Sam",
        "body": "Out of milk",
        "url": "/household/messages",
        "badge": 2,
    }


def test_the_key_is_kept(tmp_path):
    key_file = tmp_path / web_push.KEY_FILE
    first = web_push._load_vapid(key_file)
    web_push._load_vapid.cache_clear()
    second = web_push._load_vapid(key_file)
    assert key_file.is_file()
    assert first.public_pem() == second.public_pem()
