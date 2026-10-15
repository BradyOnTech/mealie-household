from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import UUID4

from mealie.core.root_logger import get_logger
from mealie.routes._base import controller
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.mixins import HttpRepo
from mealie.schema.group.ai_providers import (
    AIProviderCreate,
    AIProviderOut,
    AIProviderSettingsOut,
    AIProviderSettingsUpdate,
    AIProviderTestResult,
    AIProviderType,
    AIProviderUpdate,
    ChatGPTLoginOut,
)
from mealie.schema.response import ErrorResponse
from mealie.services.openai import OpenAIService
from mealie.services.openai.chatgpt import (
    ChatGPTError,
    ChatGPTLogin,
    attach_chatgpt_credential,
    chatgpt_logins,
)

logger = get_logger()
settings_router = APIRouter(prefix="/groups/ai-providers/settings", tags=["Groups: AI Provider Settings"])
providers_router = APIRouter(prefix="/groups/ai-providers/providers", tags=["Groups: AI Providers"])
chatgpt_login_router = APIRouter(prefix="/groups/ai-providers/chatgpt-login", tags=["Groups: AI Providers"])


@controller(settings_router)
class GroupAIProviderSettingsController(BaseUserController):
    @settings_router.get("", response_model=AIProviderSettingsOut)
    def get_ai_provider_settings(self) -> AIProviderSettingsOut:
        self.checks.can_manage()

        return self.repos.group_ai_provider_settings.get_one(self.group_id)

    @settings_router.put("", response_model=AIProviderSettingsOut)
    def update_ai_provider_settings(self, settings: AIProviderSettingsUpdate) -> AIProviderSettingsOut:
        self.checks.can_manage()

        return self.repos.group_ai_provider_settings.update(self.group_id, settings)


@controller(providers_router)
class GroupAIProviderController(BaseUserController):
    @property
    def mixins(self):
        return HttpRepo[AIProviderCreate, AIProviderOut, AIProviderCreate](self.repos.group_ai_providers, self.logger)

    def _with_chatgpt_credential(self, data: AIProviderCreate) -> AIProviderCreate:
        try:
            return attach_chatgpt_credential(data, self.user.id)
        except ChatGPTError as e:
            raise e.as_http_error() from e

    def _chatgpt_login(self, data: AIProviderCreate) -> ChatGPTLogin | None:
        """The sign-in a ChatGPT provider is being tested with, if it names one"""
        if data.provider_type != AIProviderType.chatgpt or not data.chatgpt_login_id:
            return None

        login = chatgpt_logins.get(data.chatgpt_login_id, self.user.id)
        if not login or not login.credential:
            raise ChatGPTError("That ChatGPT sign-in has expired. Sign in again.").as_http_error()
        return login

    @providers_router.post("", response_model=AIProviderOut)
    def create_ai_provider(self, data: AIProviderCreate) -> AIProviderOut:
        self.checks.can_manage()

        provider = self.mixins.create_one(self._with_chatgpt_credential(data))
        if data.chatgpt_login_id:
            chatgpt_logins.forget(data.chatgpt_login_id)
        return provider

    @providers_router.post("/test", response_model=AIProviderTestResult)
    async def test_ai_provider(self, data: AIProviderCreate) -> AIProviderTestResult:
        """Test connectivity for a provider configuration before it has been saved."""
        self.checks.can_manage()

        login = self._chatgpt_login(data)
        if data.provider_type == AIProviderType.chatgpt and not login:
            return AIProviderTestResult(success=False, message="Sign in to ChatGPT first.")

        # Ephemeral provider, never persisted. A ChatGPT one takes its sign-in's id, which is
        # how the service finds that sign-in's credential.
        provider = AIProviderOut(
            id=login.id if login else uuid4(),
            name=data.name,
            provider_type=data.provider_type,
            base_url=data.base_url,
            api_key=data.api_key,
            model=data.model,
            timeout=data.timeout,
            request_headers=data.request_headers,
            request_params=data.request_params,
            chatgpt_credential=login.credential if login else None,
        )
        return await OpenAIService(self.repos).test_connection(provider)

    @providers_router.post("/{provider_id}/test", response_model=AIProviderTestResult)
    async def test_saved_ai_provider(
        self, provider_id: UUID4, overrides: AIProviderUpdate | None = None
    ) -> AIProviderTestResult:
        """
        Test connectivity for an already-saved provider.

        Accepts optional unsaved edits to test against instead of what's in the database - e.g.
        while editing a provider, the caller may have changed the model/base_url but left the API
        key blank (meaning "keep the existing one"), so a plain "unsaved" test can't be used since
        it has no way to supply that key. An `overrides.apiKey` of "" is treated the same way: keep
        the saved key rather than testing with an empty one. Likewise a ChatGPT provider keeps its
        saved sign-in unless `overrides.chatgptLoginId` names a new one.
        """
        self.checks.can_manage()

        provider = self.mixins.get_one(provider_id)
        if overrides:
            login = self._chatgpt_login(overrides)
            provider = provider.model_copy(
                update={
                    "name": overrides.name,
                    "provider_type": overrides.provider_type,
                    "base_url": overrides.base_url,
                    "model": overrides.model,
                    "timeout": overrides.timeout,
                    "request_headers": overrides.request_headers,
                    "request_params": overrides.request_params,
                    **({"api_key": overrides.api_key} if overrides.api_key else {}),
                    **({"id": login.id, "chatgpt_credential": login.credential} if login else {}),
                }
            )
        return await OpenAIService(self.repos).test_connection(provider)

    @providers_router.get("/{provider_id}", response_model=AIProviderOut)
    def get_ai_provider(self, provider_id: UUID4) -> AIProviderOut:
        self.checks.can_manage()

        return self.mixins.get_one(provider_id)

    @providers_router.put("/{provider_id}", response_model=AIProviderOut)
    def update_ai_provider(self, provider_id: UUID4, data: AIProviderUpdate) -> AIProviderOut:
        self.checks.can_manage()

        provider = self.mixins.update_one(self._with_chatgpt_credential(data), provider_id)
        if data.chatgpt_login_id:
            chatgpt_logins.forget(data.chatgpt_login_id)
        return provider

    @providers_router.delete("/{provider_id}", response_model=AIProviderOut)
    def delete_ai_provider(self, provider_id: UUID4) -> AIProviderOut:
        self.checks.can_manage()

        return self.mixins.delete_one(provider_id)


@controller(chatgpt_login_router)
class GroupChatGPTLoginController(BaseUserController):
    def _get_login(self, login_id: UUID4) -> ChatGPTLogin:
        login = chatgpt_logins.get(login_id, self.user.id)
        if not login:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message="Not found."))
        return login

    @chatgpt_login_router.post("", response_model=ChatGPTLoginOut)
    async def start_chatgpt_login(self) -> ChatGPTLoginOut:
        """
        Start signing in to a ChatGPT account, for a ChatGPT subscription provider. Returns a code
        to enter at `verificationUrl`; poll this sign-in until it's connected, then pass its id as
        the provider's `chatgptLoginId` when saving it.
        """
        self.checks.can_manage()

        try:
            login = await chatgpt_logins.start(self.user.id)
        except ChatGPTError as e:
            raise e.as_http_error() from e
        return login.out()

    @chatgpt_login_router.get("/{login_id}", response_model=ChatGPTLoginOut)
    def get_chatgpt_login(self, login_id: UUID4) -> ChatGPTLoginOut:
        self.checks.can_manage()

        return self._get_login(login_id).out()

    @chatgpt_login_router.delete("/{login_id}")
    async def cancel_chatgpt_login(self, login_id: UUID4) -> None:
        self.checks.can_manage()

        self._get_login(login_id)
        await chatgpt_logins.discard(login_id)
