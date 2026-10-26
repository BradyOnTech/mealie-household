from datetime import datetime
from urllib.parse import urlsplit

from pydantic import UUID4, ConfigDict, Field, field_validator
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.messages import HouseholdMessage
from mealie.schema._mealie import MealieModel

MAX_MESSAGE_LENGTH = 2000

PUSH_SERVICE_HOSTS = (
    "web.push.apple.com",
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
)
"""Browsers' push services. The server posts to a subscription's endpoint, so it mustn't point anywhere else."""


class HouseholdMessageSender(MealieModel):
    id: UUID4
    username: str | None = None
    full_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class HouseholdMessageCreate(MealieModel):
    text: str = Field(..., max_length=MAX_MESSAGE_LENGTH)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message text must not be empty")
        return stripped


class HouseholdMessageSave(HouseholdMessageCreate):
    group_id: UUID4
    household_id: UUID4
    user_id: UUID4


class HouseholdMessageOut(MealieModel):
    id: UUID4
    user_id: UUID4
    user: HouseholdMessageSender
    text: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [joinedload(HouseholdMessage.user)]


class HouseholdMessageList(MealieModel):
    items: list[HouseholdMessageOut]
    """Oldest first"""
    has_older: bool = False
    """Whether there are messages before the first one here"""
    unread: int = 0
    """Messages from others since the user last read the conversation"""


class HouseholdMessageUnread(MealieModel):
    unread: int = 0
    last_message: HouseholdMessageOut | None = None


class HouseholdMessageReadIn(MealieModel):
    read_at: datetime | None = None
    """The newest message the user has seen; leave it out for now"""


class PushKeys(MealieModel):
    p256dh: str = Field(..., min_length=1, max_length=255)
    auth: str = Field(..., min_length=1, max_length=255)


class PushSubscriptionCreate(MealieModel):
    endpoint: str = Field(..., min_length=1, max_length=2048)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        known = any(host == service or host.endswith(f".{service}") for service in PUSH_SERVICE_HOSTS)
        if parts.scheme != "https" or not known:
            raise ValueError("push endpoint must be a browser push service")
        return value


class PushSubscriptionSave(MealieModel):
    user_id: UUID4
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""


class PushSubscriptionOut(PushSubscriptionSave):
    id: UUID4
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class PushConfig(MealieModel):
    public_key: str
    """The server's VAPID public key, as the browser's `applicationServerKey`"""
    subscribed: bool = False
    """Whether the endpoint asked about is subscribed for this user"""


class PushTestResult(MealieModel):
    sent: int = 0
