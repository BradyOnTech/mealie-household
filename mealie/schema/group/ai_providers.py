import base64
import binascii
import json
import re
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


class AITask(StrEnum):
    """The jobs Mealie gives an AI provider, each of which can have its own provider, model and reasoning effort"""

    household_assistant = "household_assistant"
    recipe_source_reading = "recipe_source_reading"
    """Reading a web page or images of a recipe into a transcribed source"""
    recipe_building = "recipe_building"
    """Turning a transcribed source into a structured recipe"""
    cookbook_discovery = "cookbook_discovery"
    """Finding the recipes in an imported cookbook's pages"""
    cookbook_extraction = "cookbook_extraction"
    """Reading one recipe out of a cookbook's pages"""
    ingredient_parsing = "ingredient_parsing"
    recipe_translation = "recipe_translation"
    organizer_matching = "organizer_matching"
    """Picking tags, categories and tools for an imported recipe"""


IMAGE_TASKS = frozenset({AITask.recipe_source_reading, AITask.cookbook_discovery, AITask.cookbook_extraction})
"""Tasks that can be given images, and so can have their own image provider"""

MAX_MODEL_LENGTH = 200
_REASONING_EFFORT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
"""
Effort levels are model-dependent (OpenAI documents none, minimal, low, medium, high, xhigh and max today), so
any plain identifier is accepted rather than a fixed list that would go stale. The provider rejects one its
model doesn't support.
"""


def clean_reasoning_effort(val: Any) -> str | None:
    if val is None:
        return None
    if not isinstance(val, str):
        raise ValueError("reasoning effort must be text")

    val = val.strip().lower()
    if not val:
        return None
    if not _REASONING_EFFORT.match(val):
        raise ValueError("reasoning effort must be a single word, like low, medium or high")
    return val


def clean_model_name(val: Any) -> str | None:
    if val is None:
        return None
    if not isinstance(val, str):
        raise ValueError("model must be text")

    val = val.strip()
    if len(val) > MAX_MODEL_LENGTH:
        raise ValueError(f"model can't be longer than {MAX_MODEL_LENGTH} characters")
    return val or None


class AIProviderCreate(MealieModel):
    name: str
    provider_type: AIProviderType = AIProviderType.openai
    base_url: str | None = None
    api_key: str = Field("", exclude=True)
    model: str = ""
    """Required for API-key providers. ChatGPT providers use Codex's default model when this is blank."""
    timeout: int = 300
    reasoning_effort: str | None = None
    """
    The provider's default reasoning effort. Left empty, a ChatGPT provider uses low and an API-key provider
    sends none, so the model's own default applies.
    """

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

    @field_validator("reasoning_effort", mode="before")
    def validate_reasoning_effort(val: Any) -> str | None:
        return clean_reasoning_effort(val)

    @field_validator("model", mode="before")
    def validate_model_length(val: Any) -> Any:
        return (clean_model_name(val) or "") if isinstance(val, str) else val

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
    model: str = ""
    """Blank for a ChatGPT provider using Codex's default model"""
    reasoning_effort: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return []


class AIReasoningEffortOption(MealieModel):
    effort: str
    description: str | None = None


class AIModelOption(MealieModel):
    """A model a provider's catalog lists. Being listed doesn't mean the account is allowed to use it."""

    model: str
    display_name: str
    description: str | None = None
    is_default: bool = False
    default_reasoning_effort: str | None = None
    supported_reasoning_efforts: list[AIReasoningEffortOption] = []
    input_modalities: list[str] = []


class AIModelCatalog(MealieModel):
    discovered: bool
    """False when the models couldn't be listed, in which case a model name can still be typed in"""
    models: list[AIModelOption] = []
    message: str | None = None


class AITaskSettingBase(MealieModel):
    task: AITask
    provider_id: UUID4 | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    image_provider_id: UUID4 | None = None
    image_model: str | None = None
    image_reasoning_effort: str | None = None

    @field_validator("provider_id", "image_provider_id", mode="before")
    def validate_as_none(val: Any | None) -> Any | None:
        return val or None

    @field_validator("model", "image_model", mode="before")
    def validate_model(val: Any) -> str | None:
        return clean_model_name(val)

    @field_validator("reasoning_effort", "image_reasoning_effort", mode="before")
    def validate_reasoning_effort(val: Any) -> str | None:
        return clean_reasoning_effort(val)

    @property
    def is_empty(self) -> bool:
        return not (self.provider_id or self.image_provider_id)


class AITaskSettingUpdate(AITaskSettingBase):
    """
    One task's choices. A model or reasoning effort only applies along with the provider it's for, so neither can
    be set without one. The image choices are for tasks that read images (see `IMAGE_TASKS`).
    """

    @model_validator(mode="after")
    def validate_choices(self) -> Self:
        if not self.provider_id and (self.model or self.reasoning_effort):
            raise ValueError(f"choose a provider for {self.task.value} before choosing its model or reasoning")
        if not self.image_provider_id and (self.image_model or self.image_reasoning_effort):
            raise ValueError(f"choose an image provider for {self.task.value} before choosing its image model")
        if self.image_provider_id and self.task not in IMAGE_TASKS:
            raise ValueError(f"{self.task.value} doesn't read images, so it can't have an image provider")
        return self


class AITaskSettingOut(AITaskSettingBase):
    model_config = ConfigDict(from_attributes=True)


class AIProviderSettingsCreate(MealieModel):
    group_id: UUID4


class AIProviderSettingsUpdate(MealieModel):
    default_provider_id: UUID4 | None
    audio_provider_id: UUID4 | None
    image_provider_id: UUID4 | None
    task_settings: list[AITaskSettingUpdate] | None = None
    """Every task's choices, replacing what's saved. Left out, the saved choices are kept."""

    @field_validator("default_provider_id", "audio_provider_id", "image_provider_id", mode="before")
    def validate_as_none(val: Any | None) -> Any | None:
        return val or None

    @field_validator("task_settings")
    def validate_unique_tasks(val: list[AITaskSettingUpdate] | None) -> list[AITaskSettingUpdate] | None:
        if val is None:
            return None

        tasks = [setting.task for setting in val]
        if len(tasks) != len(set(tasks)):
            raise ValueError("each task can only be listed once")
        return [setting for setting in val if not setting.is_empty]

    def referenced_provider_ids(self) -> set[UUID4]:
        ids = {self.default_provider_id, self.audio_provider_id, self.image_provider_id}
        for setting in self.task_settings or []:
            ids |= {setting.provider_id, setting.image_provider_id}
        return {provider_id for provider_id in ids if provider_id}

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            joinedload(AIProviderSettings.default_provider),
            joinedload(AIProviderSettings.audio_provider),
            joinedload(AIProviderSettings.image_provider),
        ]


class AIProviderSettingsOut(AIProviderSettingsUpdate):
    providers: list[AIProviderSummary]
    task_settings: list[AITaskSettingOut] = []  # type: ignore[assignment]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("task_settings", mode="before")
    def validate_task_settings(val: Any) -> Any:
        return [] if val is None else val

    @model_validator(mode="after")
    def validate_providers(self) -> Self:
        existing_ids = {provider.id for provider in self.providers}
        for provider_id_name in ["default_provider_id", "audio_provider_id", "image_provider_id"]:
            if not (val := getattr(self, provider_id_name, None)):
                continue

            if val not in existing_ids:
                setattr(self, provider_id_name, None)

        # A choice whose provider is gone takes its model and reasoning with it
        for setting in self.task_settings:
            if setting.provider_id not in existing_ids:
                setting.provider_id = setting.model = setting.reasoning_effort = None
            if setting.image_provider_id not in existing_ids:
                setting.image_provider_id = setting.image_model = setting.image_reasoning_effort = None
        self.task_settings = [setting for setting in self.task_settings if not setting.is_empty]

        return self

    def task_setting(self, task: AITask | None) -> AITaskSettingOut | None:
        return next((setting for setting in self.task_settings if setting.task == task), None) if task else None

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

    @computed_field  # type: ignore[misc]
    @property
    def image_reading_tasks(self) -> list[AITask]:
        """The tasks that have a provider to read images with, their own or the group's image provider"""
        if not self.ai_enabled:
            return []
        return [
            task
            for task in AITask
            if task in IMAGE_TASKS
            and (self.image_provider_id or ((setting := self.task_setting(task)) and setting.image_provider_id))
        ]

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [
            selectinload(AIProviderSettings.providers),
            selectinload(AIProviderSettings.task_settings),
            joinedload(AIProviderSettings.default_provider),
            joinedload(AIProviderSettings.audio_provider),
            joinedload(AIProviderSettings.image_provider),
        ]
