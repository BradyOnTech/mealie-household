from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from mealie.schema._mealie import MealieModel


class AssistantRole(StrEnum):
    user = "user"
    assistant = "assistant"


class AssistantMessage(MealieModel):
    role: AssistantRole
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A message can't be blank")
        return value


class AssistantChatRequest(MealieModel):
    messages: list[AssistantMessage] = Field(min_length=1, max_length=60)
    """The conversation so far, oldest first, ending with what the user just said"""

    @model_validator(mode="after")
    def ends_with_the_user(self) -> Self:
        if self.messages[-1].role != AssistantRole.user:
            raise ValueError("The last message has to be the user's")
        return self


class AssistantAction(MealieModel):
    """A change the assistant made while answering"""

    kind: str
    """Which kind of change: "restock" for the Out of list, "mealplan" for the meal plan"""
    summary: str


class AssistantChatResponse(MealieModel):
    reply: str
    actions: list[AssistantAction] = Field(default_factory=list)
