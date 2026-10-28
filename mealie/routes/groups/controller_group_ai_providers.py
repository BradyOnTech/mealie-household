from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import UUID4

from mealie.core.root_logger import get_logger
from mealie.routes._base import controller
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.mixins import HttpRepo
from mealie.schema.group.ai_providers import (
    AIModelCatalog,
    AIProviderCreate,
    AIProviderOut,
    AIProviderSettingsOut,
    AIProviderSettingsUpdate,
    AIProviderTestResult,
    AIProviderType,
    AIProviderUpdate,
    ChatGPTLoginOut,
    ChatGPTLoginState,
)
from mealie.schema.response import ErrorResponse
from mealie.services.openai import OpenAIService
from mealie.services.openai.chatgpt import (
    ChatGPTError,
    ChatGPTLogin,
    chatgpt_logins,
    finished_chatgpt_login,
    save_with_chatgpt_login,
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

    def _chatgpt_login(self, data: AIProviderCreate) -> ChatGPTLogin | None:
        """The sign-in a ChatGPT provider is being tested with, if it names one"""
        try:
            return finished_chatgpt_login(data, self.user.id)
        except ChatGPTError as e:
            raise e.as_http_error() from e

    @providers_router.post("", response_model=AIProviderOut)
    def create_ai_provider(self, data: AIProviderCreate) -> AIProviderOut:
        self.checks.can_manage()

        provider = save_with_chatgpt_login(data, self.user.id, self.mixins.create_one)
        self.repos.group_ai_provider_settings.adopt(provider)
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
            reasoning_effort=data.reasoning_effort,
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
                    **(
                        {"reasoning_effort": overrides.reasoning_effort}
                        if "reasoning_effort" in overrides.model_fields_set
                        else {}
                    ),
                    **({"api_key": overrides.api_key} if overrides.api_key else {}),
                    **({"id": login.id, "chatgpt_credential": login.credential} if login else {}),
                }
            )
        return await OpenAIService(self.repos).test_connection(provider)

    @providers_router.get("/{provider_id}/models", response_model=AIModelCatalog)
    async def list_ai_provider_models(self, provider_id: UUID4, refresh: bool = False) -> AIModelCatalog:
        """
        The models a saved ChatGPT provider's catalog lists, with the reasoning efforts each supports. This is a
        catalog, not what the account is entitled to: only a request that succeeds shows a model can be used.
        `discovered` is false when they couldn't be listed (or for API-key providers), and a model can still be
        typed in.
        """
        self.checks.can_manage()

        provider = self.mixins.get_one(provider_id)
        return await OpenAIService(self.repos).list_models(provider, refresh=refresh)

    @providers_router.get("/{provider_id}", response_model=AIProviderOut)
    def get_ai_provider(self, provider_id: UUID4) -> AIProviderOut:
        self.checks.can_manage()

        return self.mixins.get_one(provider_id)

    @providers_router.put("/{provider_id}", response_model=AIProviderOut)
    def update_ai_provider(self, provider_id: UUID4, data: AIProviderUpdate) -> AIProviderOut:
        self.checks.can_manage()

        return save_with_chatgpt_login(
            data, self.user.id, lambda prepared: self.mixins.update_one(prepared, provider_id)
        )

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

    @chatgpt_login_router.get("/{login_id}/models", response_model=AIModelCatalog)
    async def list_chatgpt_login_models(self, login_id: UUID4) -> AIModelCatalog:
        """The models a finished sign-in's catalog lists, for choosing one before the provider is saved"""
        self.checks.can_manage()

        login = self._get_login(login_id)
        if login.state != ChatGPTLoginState.connected or not login.credential:
            return AIModelCatalog(discovered=False, message="Finish signing in to ChatGPT first.")

        # An unsaved provider takes its sign-in's id, which is how the service finds that sign-in's credential
        provider = AIProviderOut(
            id=login.id, name="ChatGPT", provider_type=AIProviderType.chatgpt, chatgpt_credential=login.credential
        )
        return await OpenAIService(self.repos).list_models(provider, account=login.account)

    @chatgpt_login_router.delete("/{login_id}")
    async def cancel_chatgpt_login(self, login_id: UUID4) -> None:
        self.checks.can_manage()

        self._get_login(login_id)
        await chatgpt_logins.discard(login_id)
