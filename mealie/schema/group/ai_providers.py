import base64
import binascii
import json
from enum import StrEnum
from typing import Any, Self

from pydantic import UUID4, ConfigDict, Field, ValidationInfo, computed_field, field_validator, model_validator
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.group.ai_providers import AIProvider, AIProviderSettings
from mealie.schema._mealie import MealieModel


class AIProviderType(StrEnum):
    openai = "openai"
    """An OpenAI-compatible API, authenticated with an API key"""

    chatgpt = "chatgpt"
    """A ChatGPT subscription, signed in through the Codex CLI"""


class AIProviderCreate(MealieModel):
    name: str
    provider_type: AIProviderType = AIProviderType.openai
    base_url: str | None = None
    api_key: str = Field("", exclude=True)
    model: str = ""
    """Required for API-key providers. ChatGPT providers use Codex's default model when this is blank."""
    timeout: int = 300

    request_headers: dict[str, str] = {}
    request_params: dict[str, str] = {}

    chatgpt_login_id: UUID4 | None = Field(None, exclude=True)
    """A finished ChatGPT sign-in whose account this provider should use (ChatGPT providers only)"""

    @field_validator("name", "api_key")
    def validate_not_empty(val: str, info: ValidationInfo) -> str:
        # ChatGPT providers sign in instead, and store an empty key
        if info.field_name == "api_key" and info.data.get("provider_type") == AIProviderType.chatgpt:
            return val

        if not val:
            raise ValueError(f"{info.field_name} cannot be empty")

        return val

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if self.provider_type == AIProviderType.openai and not self.model:
            raise ValueError("model cannot be empty")

        return self

    @field_validator("base_url", mode="before")
    def validate_as_none(val: Any | None) -> Any | None:
        return val or None

    @field_validator("timeout")
    def validate_non_negative_number(val: int, info: ValidationInfo) -> int:
        if val < 0:
            raise ValueError(f"{info.field_name} cannot be less than zero")

        return val


class AIProviderSave(AIProviderCreate):
    settings_id: UUID4


class AIProviderUpdate(AIProviderCreate): ...


class AIProviderOut(AIProviderCreate):
    id: UUID4
    chatgpt_credential: str | None = Field(None, exclude=True)

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[misc]
    @property
    def chatgpt_account(self) -> str | None:
        """Email of the ChatGPT account a ChatGPT provider is signed in to"""
        if self.provider_type != AIProviderType.chatgpt:
            return None

        return chatgpt_account_email(self.chatgpt_credential)

    @field_validator("request_headers", "request_params", mode="before")
    def wrap_headers_and_params(cls, v):
        if isinstance(v, dict):
            return v

        return {x.key_name: x.value for x in v} if v else {}

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            selectinload(AIProvider.request_headers),
            selectinload(AIProvider.request_params),
        ]


class AIProviderTestResult(MealieModel):
    success: bool
    message: str | None = None
    # None if the check above didn't succeed, so image support was never checked.
    supports_images: bool | None = None


class ChatGPTLoginState(StrEnum):
    waiting = "waiting"
    connected = "connected"
    failed = "failed"
    expired = "expired"


class ChatGPTLoginOut(MealieModel):
    """A device-code sign-in to a ChatGPT account, for a ChatGPT subscription provider"""

    id: UUID4
    state: ChatGPTLoginState
    verification_url: str | None = None
    user_code: str | None = None
    account: str | None = None
    error: str | None = None


def chatgpt_account_email(credential: str | None) -> str | None:
    """Read the account email out of the ID token in Codex's auth.json, without verifying it"""
    if not credential:
        return None

    try:
        id_token = json.loads(credential)["tokens"]["id_token"]
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except AttributeError, KeyError, IndexError, TypeError, ValueError, binascii.Error:
        return None

    email = claims.get("email") if isinstance(claims, dict) else None
    return email if isinstance(email, str) else None


class AIProviderSummary(MealieModel):
    id: UUID4
    name: str
    provider_type: AIProviderType = AIProviderType.openai

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return []


class AIProviderSettingsCreate(MealieModel):
    group_id: UUID4


class AIProviderSettingsUpdate(MealieModel):
    default_provider_id: UUID4 | None
    audio_provider_id: UUID4 | None
    image_provider_id: UUID4 | None

    @field_validator("default_provider_id", "audio_provider_id", "image_provider_id", mode="before")
    def validate_as_none(val: Any | None) -> Any | None:
        return val or None

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            joinedload(AIProviderSettings.default_provider),
            joinedload(AIProviderSettings.audio_provider),
            joinedload(AIProviderSettings.image_provider),
        ]


class AIProviderSettingsOut(AIProviderSettingsUpdate):
    providers: list[AIProviderSummary]

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_providers(self) -> Self:
        existing_ids = {provider.id for provider in self.providers}
        for provider_id_name in ["default_provider_id", "audio_provider_id", "image_provider_id"]:
            if not (val := getattr(self, provider_id_name, None)):
                continue

            if val not in existing_ids:
                setattr(self, provider_id_name, None)

        return self

    @computed_field  # type: ignore[misc]
    @property
    def ai_enabled(self) -> bool:
        return self.default_provider_id is not None

    @computed_field  # type: ignore[misc]
    @property
    def audio_provider_enabled(self) -> bool:
        return self.ai_enabled and self.audio_provider_id is not None

    @computed_field  # type: ignore[misc]
    @property
    def image_provider_enabled(self) -> bool:
        return self.ai_enabled and self.image_provider_id is not None

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            selectinload(AIProviderSettings.providers),
            joinedload(AIProviderSettings.default_provider),
            joinedload(AIProviderSettings.audio_provider),
            joinedload(AIProviderSettings.image_provider),
        ]
