"""Chatting with tools through an OpenAI-compatible API, against a scripted client"""

import copy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, Field

from mealie.core.exceptions import OpenAIServiceError, RateLimitError
from mealie.schema.grocery.grocery import GroceryStore
from mealie.schema.group.ai_providers import AIProviderOut
from mealie.services.openai.openai import (
    OpenAIChatMessage,
    OpenAIService,
    OpenAITool,
    OpenAIToolError,
    tool_parameters,
)


def completion(content: str | None = None, calls: list[dict[str, Any]] | None = None) -> ChatCompletion:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return ChatCompletion.model_validate(
        {
            "id": "completion",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-test",
            "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": message}],
        }
    )


def call(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw}}


class ScriptedCompletions:
    def __init__(self, *replies: ChatCompletion | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.requests.append(copy.deepcopy(kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat_service(monkeypatch: pytest.MonkeyPatch, completions: ScriptedCompletions) -> OpenAIService:
    repos = MagicMock()
    repos.group_ai_provider_settings.get_one.return_value = None
    service = OpenAIService(repos)
    monkeypatch.setattr(service, "get_client", lambda _: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    return service


PROVIDER = AIProviderOut(id=uuid4(), name="OpenAI", api_key="key", model="gpt-test")


def recording_tool(name: str = "add_out_of_items", result: str = "Added rice to Out of") -> tuple[OpenAITool, list]:
    seen: list[Any] = []

    async def run(arguments: Any) -> str:
        seen.append(arguments)
        return result

    return OpenAITool(name=name, description="Add things", parameters={"type": "object"}, run=run), seen


@pytest.mark.asyncio
async def test_chat_runs_tools_until_the_model_answers(monkeypatch):
    completions = ScriptedCompletions(
        completion(calls=[call("1", "add_out_of_items", {"items": [{"name": "rice"}]}), call("2", "fly", {})]),
        completion("Added rice."),
    )
    tool, seen = recording_tool()
    messages = [
        OpenAIChatMessage("user", "Hi"),
        OpenAIChatMessage("assistant", "Hello!"),
        OpenAIChatMessage("user", "We're out of rice"),
    ]

    reply = await chat_service(monkeypatch, completions).chat("Be helpful", messages, [tool], provider=PROVIDER)

    assert reply == "Added rice."
    assert seen == [{"items": [{"name": "rice"}]}]

    first, second = completions.requests
    assert first["model"] == "gpt-test"
    assert first["tools"] == [
        {
            "type": "function",
            "function": {"name": "add_out_of_items", "description": "Add things", "parameters": {"type": "object"}},
        }
    ]
    assert first["messages"] == [
        {"role": "system", "content": "Be helpful"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "We're out of rice"},
    ]
    assert [call["function"]["name"] for call in second["messages"][4]["tool_calls"]] == ["add_out_of_items", "fly"]
    assert second["messages"][5] == {"role": "tool", "tool_call_id": "1", "content": "Added rice to Out of"}
    assert second["messages"][6] == {"role": "tool", "tool_call_id": "2", "content": "There's no tool called fly."}


@pytest.mark.asyncio
async def test_tool_failures_go_back_to_the_model(monkeypatch):
    async def missing(_: Any) -> str:
        raise OpenAIToolError("That item isn't on your Out of list")

    async def broken(_: Any) -> str:
        raise RuntimeError("the database password is hunter2")

    tools = [
        OpenAITool(name="missing", description="", parameters={"type": "object"}, run=missing),
        OpenAITool(name="broken", description="", parameters={"type": "object"}, run=broken),
    ]
    completions = ScriptedCompletions(
        completion(calls=[call("1", "missing", {}), call("2", "broken", {}), call("3", "missing", "{not json")]),
        completion("Sorry, that didn't work."),
    )

    reply = await chat_service(monkeypatch, completions).chat(
        "Be helpful", [OpenAIChatMessage("user", "Remove the milk")], tools, provider=PROVIDER
    )

    assert reply == "Sorry, that didn't work."
    results = [message["content"] for message in completions.requests[1]["messages"] if message["role"] == "tool"]
    assert results == [
        "That item isn't on your Out of list",
        "That didn't work because of an error in Mealie.",
        "The arguments weren't valid JSON.",
    ]


@pytest.mark.asyncio
async def test_chat_gives_up_when_the_model_never_answers(monkeypatch):
    completions = ScriptedCompletions(*[completion(calls=[call(str(i), "add_out_of_items", {})]) for i in range(20)])
    tool, _ = recording_tool()

    with pytest.raises(OpenAIServiceError):
        await chat_service(monkeypatch, completions).chat(
            "Be helpful", [OpenAIChatMessage("user", "Loop forever")], [tool], provider=PROVIDER
        )


@pytest.mark.asyncio
async def test_chat_maps_rate_limits(monkeypatch):
    import httpx
    import openai

    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    completions = ScriptedCompletions(openai.RateLimitError("Slow down", response=response, body=None))
    tool, _ = recording_tool()

    with pytest.raises(RateLimitError):
        await chat_service(monkeypatch, completions).chat(
            "Be helpful", [OpenAIChatMessage("user", "Hi")], [tool], provider=PROVIDER
        )


@pytest.mark.asyncio
async def test_chat_has_to_end_with_the_user(monkeypatch):
    tool, _ = recording_tool()

    with pytest.raises(ValueError):
        await chat_service(monkeypatch, ScriptedCompletions()).chat(
            "Be helpful", [OpenAIChatMessage("assistant", "Hello!")], [tool], provider=PROVIDER
        )


class _Item(BaseModel):
    name: str = Field(description="What it is")
    store: GroceryStore | None = None


class _Args(BaseModel):
    items: list[_Item]


def test_tool_parameters_inline_definitions_and_drop_titles():
    schema = tool_parameters(_Args)

    assert "$defs" not in json.dumps(schema)
    assert "title" not in json.dumps(schema)
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["name"] == {"description": "What it is", "type": "string"}
    store = item["properties"]["store"]["anyOf"][0]
    assert store["enum"] == ["walmart", "cub", "aldi", "whole_foods"]
