"""
Which provider, model and reasoning effort each AI task runs on, and how the reasoning effort reaches the provider.
No network is involved: API-key providers get a fake client, and ChatGPT ones a fake `codex app-server`.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from openai.types.chat import ChatCompletion

from mealie.schema.group.ai_providers import (
    AIProviderOut,
    AIProviderSettingsOut,
    AIProviderSummary,
    AIProviderType,
    AITask,
    AITaskSettingOut,
)
from mealie.schema.openai.general import OpenAIText
from mealie.services.openai import OpenAILocalImage, chatgpt
from mealie.services.openai.openai import OpenAIChatMessage, OpenAINotEnabledException, OpenAIService
from mealie.services.openai.routing import AIRoute, AIRouteSource, apply_route, resolve_ai_route
from tests.unit_tests.services_tests.test_chatgpt_service import CREDENTIAL, _recorded, fake_codex  # noqa: F401

CHATGPT = AIProviderOut(
    id=uuid4(), name="ChatGPT", provider_type=AIProviderType.chatgpt, model="", chatgpt_credential=CREDENTIAL
)
API = AIProviderOut(id=uuid4(), name="OpenAI", api_key="key", model="gpt-api")
VISION = AIProviderOut(id=uuid4(), name="Vision", api_key="key", model="gpt-vision", reasoning_effort="medium")
PROVIDERS = {provider.id: provider for provider in (CHATGPT, API, VISION)}


def _settings(*task_settings: AITaskSettingOut, default=CHATGPT, image=CHATGPT) -> AIProviderSettingsOut:
    return AIProviderSettingsOut(
        default_provider_id=default.id if default else None,
        audio_provider_id=None,
        image_provider_id=image.id if image else None,
        providers=[AIProviderSummary(id=p.id, name=p.name, provider_type=p.provider_type) for p in PROVIDERS.values()],
        task_settings=list(task_settings),
    )


def _service(settings: AIProviderSettingsOut | None, providers: dict = PROVIDERS) -> OpenAIService:
    repos = MagicMock()
    repos.group_ai_provider_settings.get_one.return_value = settings
    repos.group_ai_providers.get_one.side_effect = providers.get
    repos.group_ai_providers.get_chatgpt_credential.return_value = None
    return OpenAIService(repos)


# =======================================================================
# Resolving routes


def test_tasks_without_choices_use_the_group_providers():
    settings = _settings()
    for task in AITask:
        assert resolve_ai_route(settings, task, images=False) == AIRoute(CHATGPT.id, AIRouteSource.group_default)
    assert resolve_ai_route(settings, AITask.cookbook_discovery, images=True) == AIRoute(
        CHATGPT.id, AIRouteSource.group_images
    )
    # A request without a task (the admin debug page, say) works as it always has
    assert resolve_ai_route(settings, None, images=False) == AIRoute(CHATGPT.id, AIRouteSource.group_default)


def test_a_task_choice_applies_to_that_task_only():
    choice = AITaskSettingOut(task=AITask.recipe_building, provider_id=API.id, model="gpt-big", reasoning_effort="high")
    settings = _settings(choice)

    assert resolve_ai_route(settings, AITask.recipe_building, images=False) == AIRoute(
        API.id, AIRouteSource.task, "gpt-big", "high"
    )
    assert resolve_ai_route(settings, AITask.recipe_translation, images=False).provider_id == CHATGPT.id  # type: ignore[union-attr]


def test_a_task_provider_is_never_used_for_its_images():
    choice = AITaskSettingOut(task=AITask.recipe_source_reading, provider_id=API.id)

    assert resolve_ai_route(_settings(choice), AITask.recipe_source_reading, images=True) == AIRoute(
        CHATGPT.id, AIRouteSource.group_images
    )
    assert resolve_ai_route(_settings(choice, image=None), AITask.recipe_source_reading, images=True) is None


def test_a_task_image_provider_is_used_for_its_images():
    choice = AITaskSettingOut(
        task=AITask.cookbook_extraction,
        image_provider_id=VISION.id,
        image_model="gpt-vision-2",
        image_reasoning_effort="low",
    )
    settings = _settings(choice, image=None)

    assert resolve_ai_route(settings, AITask.cookbook_extraction, images=True) == AIRoute(
        VISION.id, AIRouteSource.task_images, "gpt-vision-2", "low"
    )
    # Text still goes to the default provider
    assert resolve_ai_route(settings, AITask.cookbook_extraction, images=False).provider_id == CHATGPT.id  # type: ignore[union-attr]
    assert resolve_ai_route(settings, AITask.cookbook_discovery, images=True) is None


def test_apply_route_keeps_the_account_and_overrides_model_and_effort():
    routed = apply_route(VISION, AIRoute(VISION.id, AIRouteSource.task, "other-model", "high"))
    assert (routed.id, routed.api_key, routed.model, routed.reasoning_effort) == (
        VISION.id,
        "key",
        "other-model",
        "high",
    )

    # Nothing chosen keeps the provider's own model and effort
    assert apply_route(VISION, AIRoute(VISION.id, AIRouteSource.group_default)) is VISION


def test_settings_out_drops_choices_for_providers_that_are_gone():
    gone = uuid4()
    settings = _settings(
        AITaskSettingOut(task=AITask.recipe_building, provider_id=gone, model="m", reasoning_effort="high"),
        AITaskSettingOut(task=AITask.cookbook_discovery, provider_id=API.id, image_provider_id=gone, image_model="m"),
    )
    assert [s.task for s in settings.task_settings] == [AITask.cookbook_discovery]
    assert settings.task_settings[0].image_provider_id is None
    assert settings.task_settings[0].image_model is None


def test_image_reading_tasks():
    assert _settings().image_reading_tasks == [
        AITask.recipe_source_reading,
        AITask.cookbook_discovery,
        AITask.cookbook_extraction,
    ]
    only_extraction = _settings(
        AITaskSettingOut(task=AITask.cookbook_extraction, image_provider_id=VISION.id), image=None
    )
    assert only_extraction.image_reading_tasks == [AITask.cookbook_extraction]
    assert _settings(default=None).image_reading_tasks == []


# =======================================================================
# The service


def test_provider_for_applies_the_task_choice():
    service = _service(
        _settings(AITaskSettingOut(task=AITask.ingredient_parsing, provider_id=VISION.id, model="gpt-parse"))
    )

    provider = service.provider_for(AITask.ingredient_parsing)
    assert (provider.id, provider.model, provider.reasoning_effort) == (VISION.id, "gpt-parse", "medium")
    assert service.provider_for(AITask.recipe_building).id == CHATGPT.id


def test_a_missing_chosen_provider_fails_rather_than_falling_back():
    settings = _settings(AITaskSettingOut(task=AITask.recipe_translation, provider_id=API.id))
    service = _service(settings, providers={CHATGPT.id: CHATGPT})

    with pytest.raises(OpenAINotEnabledException, match="no longer exists"):
        service.provider_for(AITask.recipe_translation)


def test_images_without_an_image_provider_fail():
    service = _service(_settings(image=None))

    with pytest.raises(OpenAINotEnabledException, match="No image provider"):
        service.provider_for(AITask.recipe_source_reading, images=True)
    assert service.can_read_images(AITask.recipe_source_reading) is False


def test_can_read_images_per_task():
    settings = _settings(AITaskSettingOut(task=AITask.cookbook_discovery, image_provider_id=VISION.id), image=None)
    service = _service(settings)

    assert service.can_read_images(AITask.cookbook_discovery) is True
    assert service.can_read_images(AITask.cookbook_extraction) is False
    # AI being off means nothing reads images, even with an image provider chosen
    assert _service(_settings(default=None)).can_read_images(AITask.cookbook_discovery) is False


# =======================================================================
# Reasoning effort, API-key providers


class _Stream:
    def __init__(self, body: str) -> None:
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self) -> str:
        return self.body


def _recording_client(calls: list[dict[str, Any]], *, chat_reply: ChatCompletion | None = None):
    body = json.dumps(
        {
            "id": "c",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"text": "ok"}'}}
            ],
        }
    )

    def parse(**kwargs):
        calls.append(kwargs)
        return _Stream(body)

    async def create(**kwargs):
        calls.append(kwargs)
        return chat_reply

    completions = SimpleNamespace(create=create, with_streaming_response=SimpleNamespace(parse=parse))
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


@pytest.mark.asyncio
async def test_api_key_providers_send_no_reasoning_unless_chosen(monkeypatch):
    calls: list[dict[str, Any]] = []
    service = _service(_settings(default=API))
    monkeypatch.setattr(service, "get_client", lambda _: _recording_client(calls))

    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, task=AITask.recipe_building)

    assert calls[0]["model"] == "gpt-api"
    assert "reasoning_effort" not in calls[0]


@pytest.mark.asyncio
async def test_api_key_providers_send_the_chosen_reasoning(monkeypatch):
    calls: list[dict[str, Any]] = []
    settings = _settings(
        AITaskSettingOut(task=AITask.recipe_building, provider_id=API.id, reasoning_effort="high"), default=API
    )
    service = _service(settings)
    monkeypatch.setattr(service, "get_client", lambda _: _recording_client(calls))

    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, task=AITask.recipe_building)
    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, task=AITask.recipe_translation)

    assert calls[0]["reasoning_effort"] == "high"
    # The task without a choice runs on the same provider exactly as before
    assert "reasoning_effort" not in calls[1]


@pytest.mark.asyncio
async def test_the_assistant_sends_its_reasoning_with_its_tools(monkeypatch):
    calls: list[dict[str, Any]] = []
    reply = ChatCompletion.model_validate(
        {
            "id": "c",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hello"}}],
        }
    )
    settings = _settings(
        AITaskSettingOut(task=AITask.household_assistant, provider_id=VISION.id, model="gpt-chat"), default=API
    )
    service = _service(settings)
    monkeypatch.setattr(service, "get_client", lambda _: _recording_client(calls, chat_reply=reply))

    text = await service.chat(
        "Be helpful", [OpenAIChatMessage(role="user", content="Hi")], [], task=AITask.household_assistant
    )

    assert text == "Hello"
    assert calls[0]["model"] == "gpt-chat"
    # The provider's own effort, since the task didn't choose one
    assert calls[0]["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_images_go_to_the_task_image_provider(monkeypatch, tmp_path):
    calls: list[dict[str, Any]] = []
    clients: list[AIProviderOut] = []
    settings = _settings(
        AITaskSettingOut(task=AITask.recipe_source_reading, image_provider_id=VISION.id, image_reasoning_effort="low"),
        default=API,
        image=None,
    )
    service = _service(settings)

    def get_client(provider):
        clients.append(provider)
        return _recording_client(calls)

    monkeypatch.setattr(service, "get_client", get_client)
    image = tmp_path / "page.jpg"
    from PIL import Image

    Image.new("RGB", (8, 8)).save(image)

    await service.get_response(
        "Prompt",
        "Read this",
        response_schema=OpenAIText,
        attachments=[OpenAILocalImage(filename="page.jpg", path=image)],
        task=AITask.recipe_source_reading,
    )

    assert clients[0].id == VISION.id
    assert calls[0]["model"] == "gpt-vision"
    assert calls[0]["reasoning_effort"] == "low"


# =======================================================================
# Reasoning effort, ChatGPT providers


@pytest.mark.asyncio
async def test_chatgpt_providers_keep_low_reasoning_by_default(fake_codex):  # noqa: F811
    record = fake_codex()
    service = _service(_settings())

    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, task=AITask.recipe_building)

    assert _recorded(record, "turn")["effort"] == chatgpt.REASONING_EFFORT == "low"
    assert "model" not in _recorded(record, "thread")


@pytest.mark.asyncio
async def test_chatgpt_providers_use_the_task_model_and_reasoning(fake_codex):  # noqa: F811
    record = fake_codex()
    settings = _settings(
        AITaskSettingOut(
            task=AITask.cookbook_discovery, provider_id=CHATGPT.id, model="deep-model", reasoning_effort="high"
        )
    )
    service = _service(settings)

    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, task=AITask.cookbook_discovery)

    assert _recorded(record, "turn")["effort"] == "high"
    assert _recorded(record, "thread")["model"] == "deep-model"


@pytest.mark.asyncio
async def test_chatgpt_provider_reasoning_default(fake_codex):  # noqa: F811
    record = fake_codex()
    provider = CHATGPT.model_copy(update={"reasoning_effort": "medium"})
    service = _service(_settings(), providers={CHATGPT.id: provider})

    await service.chat(
        "Be helpful", [OpenAIChatMessage(role="user", content="Hi")], [], task=AITask.household_assistant
    )

    assert _recorded(record, "turn")["effort"] == "medium"
