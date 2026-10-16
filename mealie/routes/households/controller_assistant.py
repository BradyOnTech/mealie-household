from fastapi import APIRouter, HTTPException, status

from mealie.core.exceptions import RateLimitError
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.schema.assistant.assistant import AssistantChatRequest, AssistantChatResponse
from mealie.schema.response.responses import ErrorResponse
from mealie.services.household_services.assistant import HouseholdAssistant
from mealie.services.openai.chatgpt import ChatGPTError
from mealie.services.openai.openai import OpenAINotEnabledException

router = APIRouter(prefix="/households/assistant", tags=["Households: Assistant"])


@controller(router)
class HouseholdAssistantController(BaseUserController):
    @router.post("/chat", response_model=AssistantChatResponse)
    async def chat(self, data: AssistantChatRequest) -> AssistantChatResponse:
        """Reply to the household's chat with the assistant, which can read and change their groceries and plans"""
        try:
            return await HouseholdAssistant(self.repos, self.user).reply(data.messages)
        except OpenAINotEnabledException as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(message=e.message)) from e
        except ChatGPTError as e:
            raise e.as_http_error() from e
        except RateLimitError as e:
            message = "The AI provider's usage limit was reached. Try again later."
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=ErrorResponse.respond(message=message)) from e
        except Exception as e:
            # Don't echo provider errors back: their bodies can include whatever a base URL points at
            self.logger.exception("The household assistant couldn't reply")
            message = "The assistant couldn't reply just now. Try again in a moment."
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=ErrorResponse.respond(message=message)) from e
