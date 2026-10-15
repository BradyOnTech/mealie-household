from fastapi import APIRouter
from pydantic import UUID4

from mealie.repos.repository_factory import AllRepositories
from mealie.routes._base import BaseAdminController, controller
from mealie.routes._base.mixins import HttpRepo
from mealie.schema.group.ai_providers import (
    AIProviderCreate,
    AIProviderOut,
    AIProviderUpdate,
)
from mealie.services.openai.chatgpt import ChatGPTError, attach_chatgpt_credential, chatgpt_logins

router = APIRouter(prefix="/groups/{group_id}/ai-providers")


@controller(router)
class AdminGroupAIProviderController(BaseAdminController):
    def _group_repos(self, group_id: UUID4) -> AllRepositories:
        """Return repos scoped to the target group."""
        return AllRepositories(self.session, group_id=group_id, household_id=None)

    def _mixins(self, group_id: UUID4) -> HttpRepo:
        return HttpRepo[AIProviderCreate, AIProviderOut, AIProviderCreate](
            self._group_repos(group_id).group_ai_providers, self.logger
        )

    # =======================================================================
    # Provider CRUD

    def _with_chatgpt_credential(self, data: AIProviderCreate) -> AIProviderCreate:
        try:
            return attach_chatgpt_credential(data, self.user.id)
        except ChatGPTError as e:
            raise e.as_http_error() from e

    @router.post("/providers", response_model=AIProviderOut, tags=["Admin: AI Providers"])
    def create_ai_provider(self, group_id: UUID4, data: AIProviderCreate):
        provider = self._mixins(group_id).create_one(self._with_chatgpt_credential(data))
        if data.chatgpt_login_id:
            chatgpt_logins.forget(data.chatgpt_login_id)
        return provider

    @router.get("/providers/{provider_id}", response_model=AIProviderOut, tags=["Admin: AI Providers"])
    def get_ai_provider(self, group_id: UUID4, provider_id: UUID4):
        return self._mixins(group_id).get_one(provider_id)

    @router.put("/providers/{provider_id}", response_model=AIProviderOut, tags=["Admin: AI Providers"])
    def update_ai_provider(self, group_id: UUID4, provider_id: UUID4, data: AIProviderUpdate):
        provider = self._mixins(group_id).update_one(self._with_chatgpt_credential(data), provider_id)
        if data.chatgpt_login_id:
            chatgpt_logins.forget(data.chatgpt_login_id)
        return provider

    @router.delete("/providers/{provider_id}", response_model=AIProviderOut, tags=["Admin: AI Providers"])
    def delete_ai_provider(self, group_id: UUID4, provider_id: UUID4):
        return self._mixins(group_id).delete_one(provider_id)
