from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException, status
from pydantic import UUID4, BaseModel, ValidationError

from mealie.db.models.group.ai_providers import AIProvider, AIProviderSettings, AITaskSetting
from mealie.schema.group.ai_providers import (
    AIProviderCreate,
    AIProviderOut,
    AIProviderSettingsOut,
    AIProviderSettingsUpdate,
    AIProviderType,
    AITaskSettingUpdate,
)

from .repository_generic import GroupRepositoryGeneric


def _check_credentials(data: dict) -> None:
    if data.get("provider_type") == AIProviderType.chatgpt:
        if not data.get("chatgpt_credential"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Sign in to ChatGPT before saving this provider")
    elif not data.get("api_key"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="API key cannot be empty")


class GroupRepositoryAIProvider(GroupRepositoryGeneric[AIProviderOut, AIProvider]):
    def _group_settings_id(self):
        return sa.select(AIProviderSettings.id).where(AIProviderSettings.group_id == self.group_id).scalar_subquery()

    def create(self, data: AIProviderCreate | dict):
        if isinstance(data, AIProviderCreate):
            api_key = data.api_key
            data = data.model_dump()
            data["api_key"] = api_key

        _check_credentials(data)
        if data.get("provider_type") == AIProviderType.chatgpt:
            data["api_key"] = ""

        if not data.get("settings_id"):
            data["settings_id"] = self.session.execute(
                sa.select(AIProviderSettings.id).where(AIProviderSettings.group_id == self.group_id)
            ).scalar_one()

        return super().create(data)

    def update(self, match_value: str | int | UUID4, new_data: AIProviderCreate | dict):
        if isinstance(new_data, AIProviderCreate):
            # api_key is excluded from the schema's dump, so carry it over by hand, the same
            # way create does. Without this every update looks like it omitted the key.
            api_key = new_data.api_key
            fields_set = new_data.model_fields_set
            new_data = new_data.model_dump()
            new_data["api_key"] = api_key
            # A client from before reasoning effort existed leaves it out, which mustn't clear a saved one
            if "reasoning_effort" not in fields_set:
                new_data.pop("reasoning_effort", None)

        # Keep the existing credentials unless new ones were given
        existing = self.get_one(match_value)
        if existing:
            if not new_data.get("api_key"):
                new_data["api_key"] = existing.api_key
            new_data.setdefault("provider_type", existing.provider_type)

        if new_data.get("provider_type") == AIProviderType.chatgpt:
            if not new_data.get("chatgpt_credential") and existing:
                _check_credentials({**new_data, "chatgpt_credential": existing.chatgpt_credential})
            else:
                _check_credentials(new_data)
            # Don't leave an unused API key lying around
            new_data["api_key"] = ""
        else:
            _check_credentials(new_data)
            new_data["chatgpt_credential"] = None

        return super().update(match_value, new_data)

    def get_chatgpt_credential(self, provider_id: UUID4) -> str | None:
        """Read straight from the database, rather than from any copy of the row this session holds"""
        return self.session.execute(
            sa.select(AIProvider.chatgpt_credential).where(
                AIProvider.id == provider_id, AIProvider.settings_id == self._group_settings_id()
            )
        ).scalar_one_or_none()

    def set_chatgpt_credential(self, provider_id: UUID4, credential: str) -> None:
        self.session.execute(
            sa.update(AIProvider)
            .where(AIProvider.id == provider_id, AIProvider.settings_id == self._group_settings_id())
            .values(chatgpt_credential=credential)
            .execution_options(synchronize_session=False)
        )
        self.session.commit()

    def delete(self, value, match_key: str | None = None) -> AIProviderOut:
        # Null out any settings references to this provider before deleting
        self.session.execute(
            sa.update(AIProviderSettings)
            .where(AIProviderSettings.default_provider_id == value)
            .values(default_provider_id=None)
        )
        self.session.execute(
            sa.update(AIProviderSettings)
            .where(AIProviderSettings.audio_provider_id == value)
            .values(audio_provider_id=None)
        )
        self.session.execute(
            sa.update(AIProviderSettings)
            .where(AIProviderSettings.image_provider_id == value)
            .values(image_provider_id=None)
        )
        # A task's model and reasoning were chosen for this provider, so they go with it
        self.session.execute(
            sa.update(AITaskSetting)
            .where(AITaskSetting.provider_id == value)
            .values(provider_id=None, model=None, reasoning_effort=None)
            .execution_options(synchronize_session=False)
        )
        self.session.execute(
            sa.update(AITaskSetting)
            .where(AITaskSetting.image_provider_id == value)
            .values(image_provider_id=None, image_model=None, image_reasoning_effort=None)
            .execution_options(synchronize_session=False)
        )
        self.session.execute(
            sa.delete(AITaskSetting)
            .where(AITaskSetting.provider_id.is_(None), AITaskSetting.image_provider_id.is_(None))
            .execution_options(synchronize_session=False)
        )

        # Delete
        return super().delete(value, match_key)

    def update_many(self, data):
        raise NotImplementedError


ROLE_FIELDS = ("default_provider_id", "audio_provider_id", "image_provider_id")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail)


class GroupRepositoryAIProviderSettings(GroupRepositoryGeneric[AIProviderSettingsOut, AIProviderSettings]):
    @staticmethod
    def _read_update(new_data: dict | BaseModel, settings: AIProviderSettings) -> AIProviderSettingsUpdate:
        """
        Only the provider choices are taken from `new_data`; anything else on it (like the providers themselves,
        when it's a whole `AIProviderSettingsOut`) is ignored, and a choice it leaves out keeps its saved value.
        Task choices are left as None, meaning "keep the saved ones", unless `new_data` has them.
        """
        raw: dict[str, Any] = new_data if isinstance(new_data, dict) else new_data.__dict__
        tasks = raw.get("task_settings")
        try:
            return AIProviderSettingsUpdate.model_validate(
                {
                    **{field: raw.get(field, getattr(settings, field)) for field in ROLE_FIELDS},
                    "task_settings": None
                    if tasks is None
                    else [task.model_dump() if isinstance(task, BaseModel) else task for task in tasks],
                }
            )
        except ValidationError as e:
            raise _bad_request(f"Invalid AI settings: {e.errors()[0].get('msg', 'invalid value')}") from e

    def update(self, match_value: str | int | UUID4, new_data: dict | BaseModel) -> AIProviderSettingsOut:
        # The query is scoped to this repository's group, so another group's settings are never found
        settings = self._query_one(match_value)
        update = self._read_update(new_data, settings)
        types = self._provider_types(settings.id, update.referenced_provider_ids())

        if update.audio_provider_id and types[update.audio_provider_id] == AIProviderType.chatgpt:
            raise _bad_request(
                "A ChatGPT subscription provider can't transcribe audio, so it can't be the audio provider"
            )

        if update.task_settings is not None:
            self.session.execute(
                sa.delete(AITaskSetting)
                .where(AITaskSetting.settings_id == settings.id)
                .execution_options(synchronize_session=False)
            )
            for task_setting in update.task_settings:
                self.session.add(self._task_row(settings.id, task_setting))
            # Re-read the collection, rather than trusting the copy loaded before the rows were replaced
            self.session.flush()
            self.session.expire(settings, ["task_settings"])

        return super().update(match_value, {field: getattr(update, field) for field in ROLE_FIELDS})

    def _provider_types(self, settings_id: UUID4, provider_ids: set[UUID4]) -> dict[UUID4, str]:
        """
        The type of each provider, which must all belong to the same group as the settings. One from another group
        is refused, so settings can never point a group's AI requests at someone else's account.
        """
        if not provider_ids:
            return {}

        rows = self.session.execute(
            sa.select(AIProvider.id, AIProvider.provider_type).where(
                AIProvider.settings_id == settings_id, AIProvider.id.in_(provider_ids)
            )
        ).all()
        types = {row.id: row.provider_type for row in rows}
        if set(types) != provider_ids:
            raise _bad_request("That AI provider doesn't exist in this group")
        return types

    def _task_row(self, settings_id: UUID4, task_setting: AITaskSettingUpdate) -> AITaskSetting:
        return AITaskSetting(
            session=self.session,
            settings_id=settings_id,
            **{**task_setting.model_dump(), "task": task_setting.task.value},
        )

    def adopt(self, provider: AIProviderOut) -> AIProviderSettingsOut | None:
        """
        Give a provider someone just added the jobs no provider has yet, so a group's first provider turns AI on
        without a second step. It becomes the default provider, and a ChatGPT one, which reads images, the image
        provider too. Audio is left alone: a ChatGPT provider can't transcribe, and whether an API-key one can
        depends on its model.
        """
        settings = self.get_one(self.group_id) if self.group_id else None
        if settings is None:
            return None

        updates: dict[str, UUID4] = {}
        if not settings.default_provider_id:
            updates["default_provider_id"] = provider.id
        if not settings.image_provider_id and provider.provider_type == AIProviderType.chatgpt:
            updates["image_provider_id"] = provider.id
        if not updates:
            return settings

        return self.update(
            self.group_id,
            {
                "default_provider_id": settings.default_provider_id,
                "audio_provider_id": settings.audio_provider_id,
                "image_provider_id": settings.image_provider_id,
                **updates,
            },
        )
