import sqlalchemy as sa
from fastapi import HTTPException, status
from pydantic import UUID4, BaseModel

from mealie.db.models.group.ai_providers import AIProvider, AIProviderSettings
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderOut, AIProviderSettingsOut, AIProviderType

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
            new_data = new_data.model_dump()
            new_data["api_key"] = api_key

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

        # Delete
        return super().delete(value, match_key)

    def update_many(self, data):
        raise NotImplementedError


class GroupRepositoryAIProviderSettings(GroupRepositoryGeneric[AIProviderSettingsOut, AIProviderSettings]):
    def update(self, match_value: str | int | UUID4, new_data: dict | BaseModel) -> AIProviderSettingsOut:
        new_data = new_data if isinstance(new_data, dict) else new_data.model_dump()

        if audio_provider_id := new_data.get("audio_provider_id"):
            provider_type = self.session.execute(
                sa.select(AIProvider.provider_type).where(AIProvider.id == audio_provider_id)
            ).scalar_one_or_none()
            if provider_type == AIProviderType.chatgpt:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="A ChatGPT subscription provider can't transcribe audio, so it can't be the audio provider",
                )

        return super().update(match_value, new_data)
