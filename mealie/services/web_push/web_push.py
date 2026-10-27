"""
Web Push: notifications sent to the installed app, through each browser's push service (Apple's for iPhones).

The server signs what it sends with a VAPID key pair, generated on first use and kept in the data directory
like the app's other secrets. Browsers subscribe with its public half, so replacing the key file means every
device has to turn notifications on again.
"""

import ipaddress
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from py_vapid.utils import b64urlencode
from pywebpush import WebPushException, webpush

from mealie.core.config import get_app_dirs, get_app_settings
from mealie.core.root_logger import get_logger
from mealie.schema.messages.messages import PushSubscriptionOut

KEY_FILE = ".vapid_private.pem"
TTL = 24 * 60 * 60
"""How long a push service holds a notification for a device that's offline, in seconds"""
TIMEOUT = 10
FALLBACK_SUBJECT = "https://mealie.io"
"""For servers without a public https address or an email to give; set WEB_PUSH_SUBJECT to name yourself"""

logger = get_logger()


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    url: str = "/"
    tag: str | None = None
    badge: int | None = None
    """The number to show on the app's icon"""

    def payload(self) -> str:
        data: dict[str, str | int] = {"title": self.title, "body": self.body, "url": self.url}
        if self.tag:
            data["tag"] = self.tag
        if self.badge is not None:
            data["badge"] = self.badge
        return json.dumps(data)


class SubscriptionGone(Exception):
    """The push service no longer knows the subscription: the app was removed or notifications turned off"""


@lru_cache
def _load_vapid(key_file: Path) -> Vapid:
    if key_file.is_file():
        return Vapid.from_file(str(key_file))

    vapid = Vapid()
    vapid.generate_keys()
    tmp_file = key_file.with_suffix(".tmp")
    vapid.save_key(str(tmp_file))
    os.chmod(tmp_file, 0o600)
    tmp_file.replace(key_file)
    logger.info("Generated a Web Push (VAPID) key")
    return vapid


def get_vapid() -> Vapid:
    return _load_vapid(get_app_dirs().DATA_DIR / KEY_FILE)


def public_key() -> str:
    """The VAPID public key in the form browsers take as `applicationServerKey`"""
    raw = get_vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64urlencode(raw)


def _public_host(host: str | None) -> bool:
    """Whether a push service would take `host` as a contact: Apple rejects localhost, and IPs aren't names"""
    if not host or host == "localhost" or host.endswith(".local") or "." not in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


def subject() -> str:
    """
    Who push services can contact about this server: a `mailto:` or an https URL without a port. Apple
    rejects a token without one, or with a localhost one.
    """
    settings = get_app_settings()
    if settings.WEB_PUSH_SUBJECT:
        return settings.WEB_PUSH_SUBJECT
    parts = urlsplit(settings.BASE_URL)
    if parts.scheme == "https" and _public_host(parts.hostname):
        return f"https://{parts.hostname}"
    if settings.SMTP_FROM_EMAIL:
        return f"mailto:{settings.SMTP_FROM_EMAIL}"
    return FALLBACK_SUBJECT


def send(subscription: PushSubscriptionOut, message: PushMessage) -> None:
    """Send one notification. Raises `SubscriptionGone` when the subscription should be forgotten."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=message.payload(),
            vapid_private_key=get_vapid(),
            # A fresh dict each time: webpush fills in the audience and expiry for the endpoint it's given
            vapid_claims={"sub": subject()},
            ttl=TTL,
            timeout=TIMEOUT,
            headers={"Urgency": "high"},
        )
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else None
        if status in (404, 410):
            raise SubscriptionGone from e
        raise
