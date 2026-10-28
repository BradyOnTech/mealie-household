"""
Which provider, model and reasoning effort an AI request runs on.

Every request is for a task (see `AITask`) and either reads images or doesn't. Each choice falls back on its own:

* Without images, a task uses its own provider if it has one, and otherwise the group's default provider.
* With images, a task uses its own image provider if it has one, and otherwise the group's image provider. A
  task's text provider is never used for images, so choosing one can't quietly route images to a provider that
  can't read them.
* The model and reasoning effort come from the task's choice when it set them, and otherwise from the provider
  the request ended up on.

Nothing here falls back from a provider that's been chosen to a different one: a request whose provider is
missing fails instead, so it never runs on (or is billed to) an account nobody picked for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import UUID4

from mealie.schema.group.ai_providers import AIProviderOut, AIProviderSettingsOut, AITask


class AIRouteSource(StrEnum):
    task = "task"
    task_images = "task_images"
    group_default = "group_default"
    group_images = "group_images"


@dataclass(frozen=True)
class AIRoute:
    provider_id: UUID4
    source: AIRouteSource
    model: str | None = None
    """None to use the provider's model"""
    reasoning_effort: str | None = None
    """None to use the provider's reasoning effort"""


def resolve_ai_route(settings: AIProviderSettingsOut | None, task: AITask | None, *, images: bool) -> AIRoute | None:
    """The route a request takes, or None when there's no provider for it"""
    if settings is None:
        return None

    choice = settings.task_setting(task)
    if images:
        if choice and choice.image_provider_id:
            return AIRoute(
                choice.image_provider_id, AIRouteSource.task_images, choice.image_model, choice.image_reasoning_effort
            )
        if settings.image_provider_id:
            return AIRoute(settings.image_provider_id, AIRouteSource.group_images)
        return None

    if choice and choice.provider_id:
        return AIRoute(choice.provider_id, AIRouteSource.task, choice.model, choice.reasoning_effort)
    if settings.default_provider_id:
        return AIRoute(settings.default_provider_id, AIRouteSource.group_default)
    return None


def apply_route(provider: AIProviderOut, route: AIRoute) -> AIProviderOut:
    """The provider as the route uses it: same account and credentials, with the route's model and effort"""
    update: dict[str, str] = {}
    if route.model:
        update["model"] = route.model
    if route.reasoning_effort:
        update["reasoning_effort"] = route.reasoning_effort
    return provider.model_copy(update=update) if update else provider
