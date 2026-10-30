"""
Tests for ChatGPT subscription providers, run against a fake `codex app-server` that speaks just
enough of the JSON-RPC protocol, so no network or real ChatGPT account is involved.
"""

import asyncio
import base64
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from mealie.core import exceptions
from mealie.schema.group.ai_providers import (
    AIProviderCreate,
    AIProviderOut,
    AIProviderType,
    ChatGPTLoginState,
    chatgpt_account_email,
)
from mealie.schema.openai.general import OpenAIText
from mealie.services.openai import chatgpt
from mealie.services.openai.openai import OpenAIChatMessage, OpenAIService, OpenAITool

FAKE_CODEX = """
import json, os, sys, threading, time

MODE = {mode!r}
RECORD = {record!r}
ID_TOKEN = {id_token!r}

home = os.environ["CODEX_HOME"]
auth_path = os.path.join(home, "auth.json")
lock = threading.Lock()


def send(message):
    with lock:
        sys.stdout.write(json.dumps(message) + "\\n")
        sys.stdout.flush()


def record(name, value):
    with open(os.path.join(RECORD, name), "w") as f:
        json.dump(value, f)


def finish_login():
    time.sleep(0.2)
    with open(auth_path, "w") as f:
        json.dump({{"auth_mode": "chatgpt", "tokens": {{"id_token": ID_TOKEN, "access_token": "new"}}}}, f)
    send({{"method": "account/login/completed", "params": {{"loginId": "login-1", "success": True}}}})
    send({{"method": "account/updated", "params": {{"authMode": "chatgpt", "planType": "plus"}}}})


record("env", dict(os.environ))
for line in sys.stdin:
    message = json.loads(line)
    method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {{}}
    if request_id is None:
        continue

    if method == "initialize":
        send({{"id": request_id, "result": {{}}}})
    elif method == "account/read":
        signed_in = os.path.exists(auth_path) and MODE != "signed_out"
        account = {{"type": "chatgpt", "email": "cook@example.com", "planType": "plus"}} if signed_in else None
        send({{"id": request_id, "result": {{"account": account}}}})
    elif method == "thread/start":
        record("thread", params)
        send({{"id": request_id, "result": {{"thread": {{"id": "thread-1"}}}}}})
    elif method == "thread/inject_items":
        record("history", params["items"])
        send({{"id": request_id, "result": {{}}}})
    elif method == "turn/start":
        record("turn", params)
        # Simulate Codex refreshing the tokens partway through
        with open(auth_path) as f:
            credential = json.load(f)
        credential["tokens"]["access_token"] = "refreshed"
        with open(auth_path, "w") as f:
            json.dump(credential, f)

        send({{"id": request_id, "result": {{"turn": {{"id": "turn-1"}}}}}})
        if MODE == "tools":
            # Call the first tool the client offered, the way the model would, then answer with its result
            with open(os.path.join(RECORD, "thread")) as f:
                tool = json.load(f)["dynamicTools"][0]["name"]
            call = {{"threadId": "thread-1", "turnId": "turn-1", "callId": "call-1", "namespace": None, "tool": tool}}
            call["arguments"] = {{"items": [{{"name": "rice"}}]}}
            send({{"id": "codex-1", "method": "item/tool/call", "params": call}})
            response = json.loads(sys.stdin.readline())
            record("tool_response", response)
            text = response["result"]["contentItems"][0]["text"]
            item = {{"type": "agentMessage", "text": f"Tool said: {{text}}", "phase": "final_answer"}}
            turn = {{"status": "completed", "items": [item]}}
        elif MODE == "usage_limit":
            error = {{"message": "You've hit your usage limit.", "codexErrorInfo": "usageLimitExceeded"}}
            turn = {{"status": "failed", "items": [], "error": error}}
        else:
            images = sum(1 for part in params["input"] if part["type"] == "image")
            answer = json.dumps({{"text": f"{{params['input'][0]['text']}} ({{images}} images)"}})
            turn = {{
                "status": "completed",
                "items": [
                    {{"type": "agentMessage", "text": "Reading it now", "phase": "commentary"}},
                    {{"type": "agentMessage", "text": answer, "phase": "final_answer"}},
                ],
            }}
        send({{"method": "turn/completed", "params": {{"threadId": "thread-1", "turn": turn}}}})
    elif method == "model/list":
        calls = []
        if os.path.exists(os.path.join(RECORD, "model_list")):
            with open(os.path.join(RECORD, "model_list")) as f:
                calls = json.load(f)
        record("model_list", calls + [params])
        if MODE == "endless_models":
            send({{"id": request_id, "result": {{"data": [], "nextCursor": f"page-{{len(calls) + 2}}"}}}})
        elif not params.get("cursor"):
            fast = {{
                "id": "fast", "model": "fast-model", "displayName": "Fast", "description": "Quick answers",
                "hidden": False, "isDefault": True, "defaultReasoningEffort": "low",
                "supportedReasoningEfforts": [
                    {{"reasoningEffort": "low", "description": "Quickest"}},
                    {{"reasoningEffort": "medium", "description": "Balanced"}},
                ],
                "inputModalities": ["text", "image"], "futureField": {{"ignored": True}},
            }}
            hidden = dict(fast, id="hidden", model="hidden-model", hidden=True, isDefault=False)
            page = [fast, hidden, {{"displayName": "No id"}}, "junk"]
            send({{"id": request_id, "result": {{"data": page, "nextCursor": "page-2"}}}})
        else:
            deep = {{
                "id": "deep", "model": "deep-model", "displayName": "Deep", "description": "",
                "hidden": False, "isDefault": False, "defaultReasoningEffort": "high",
                "supportedReasoningEfforts": [{{"reasoningEffort": "high", "description": "Thorough"}}],
            }}
            duplicate = {{"id": "fast", "model": "fast-model", "displayName": "Fast again", "hidden": False}}
            send({{"id": request_id, "result": {{"data": [deep, duplicate], "nextCursor": None}}}})
    elif method == "account/login/start":
        send({{
            "id": request_id,
            "result": {{
                "type": "chatgptDeviceCode",
                "loginId": "login-1",
                "verificationUrl": "https://auth.openai.com/codex/device",
                "userCode": "ABCD-1234",
            }},
        }})
        if MODE != "login_never_finishes":
            threading.Thread(target=finish_login).start()
    elif method == "account/login/cancel":
        record("cancelled", True)
        send({{"id": request_id, "result": {{}}}})
    else:
        send({{"id": request_id, "error": {{"code": -32601, "message": f"unknown method {{method}}"}}}})
"""


def _id_token(email: str) -> str:
    def encode(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode({'email': email})}.signature"


CREDENTIAL = json.dumps(
    {"auth_mode": "chatgpt", "tokens": {"id_token": _id_token("cook@example.com"), "access_token": "old"}}
)


@pytest.fixture()
def fake_codex(tmp_path, monkeypatch):
    """Point Mealie at a fake Codex. Call the result with a mode to (re)write the fake's script."""
    record = tmp_path / "record"
    record.mkdir()
    script = tmp_path / "codex"

    def install(mode: str = "ok") -> Path:
        source = FAKE_CODEX.format(mode=mode, record=str(record), id_token=_id_token("cook@example.com"))
        script.write_text(f"#!{sys.executable}\n{source}")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return record

    install()
    monkeypatch.setattr(chatgpt, "get_app_settings", lambda: SimpleNamespace(CODEX_BIN=str(script)))
    return install


def _recorded(record: Path, name: str):
    return json.loads((record / name).read_text())


async def _run(**overrides):
    saved: list[str] = []
    kwargs = {
        "instructions": "Be helpful",
        "inputs": [{"type": "text", "text": "Hello"}],
        "output_schema": {"type": "object"},
        "model": None,
        "timeout": 30,
        "save_credential": saved.append,
    } | overrides
    text = await chatgpt.run_chatgpt_turn(CREDENTIAL, **kwargs)
    return text, saved


@pytest.mark.asyncio
async def test_run_chatgpt_turn_returns_the_final_answer(fake_codex):
    record = fake_codex()

    text, saved = await _run(model="gpt-test")

    assert json.loads(text) == {"text": "Hello (0 images)"}

    thread = _recorded(record, "thread")
    assert thread["baseInstructions"] == "Be helpful"
    assert thread["ephemeral"] is True
    assert thread["sandbox"] == "read-only"
    assert thread["approvalPolicy"] == "never"
    assert thread["model"] == "gpt-test"
    assert thread["config"]["features"]["shell_tool"] is False

    assert "dynamicTools" not in thread
    assert not (record / "history").exists()

    turn = _recorded(record, "turn")
    assert turn["outputSchema"] == {"type": "object"}
    assert turn["effort"] == chatgpt.REASONING_EFFORT

    # The refreshed tokens are handed back to be saved
    assert len(saved) == 1
    assert json.loads(saved[0])["tokens"]["access_token"] == "refreshed"


@pytest.mark.asyncio
async def test_run_chatgpt_turn_only_passes_codex_a_minimal_environment(fake_codex, monkeypatch):
    record = fake_codex()
    monkeypatch.setenv("POSTGRES_PASSWORD", "hunter2")

    await _run()

    env = _recorded(record, "env")
    assert "POSTGRES_PASSWORD" not in env
    assert env["CODEX_HOME"].endswith("home")


@pytest.mark.asyncio
async def test_run_chatgpt_turn_saves_refreshed_tokens_even_when_it_fails(fake_codex):
    fake_codex("usage_limit")
    saved: list[str] = []

    with pytest.raises(chatgpt.ChatGPTUsageLimitError, match="usage limit"):
        await _run(save_credential=saved.append)

    # Codex rotated the refresh token before the turn failed, so it must still be saved
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_run_chatgpt_turn_rejects_a_signed_out_credential(fake_codex):
    fake_codex("signed_out")

    with pytest.raises(chatgpt.ChatGPTAuthError):
        await _run()


@pytest.mark.asyncio
async def test_run_chatgpt_turn_without_codex_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(chatgpt, "get_app_settings", lambda: SimpleNamespace(CODEX_BIN=str(tmp_path / "missing")))

    with pytest.raises(chatgpt.ChatGPTError, match="Codex CLI isn't installed"):
        await _run()


TOOLS = [
    {
        "type": "function",
        "name": "add_out_of_items",
        "description": "Add things the household is out of",
        "inputSchema": {"type": "object"},
    }
]


@pytest.mark.asyncio
async def test_run_chatgpt_turn_offers_tools_and_answers_their_calls(fake_codex):
    record = fake_codex("tools")
    calls = []

    async def call_tool(name, arguments):
        calls.append((name, arguments))
        return True, "Added rice"

    history = [chatgpt.to_codex_history("user", "Hi"), chatgpt.to_codex_history("assistant", "Hello!")]
    text, _ = await _run(output_schema=None, tools=TOOLS, call_tool=call_tool, history=history)

    assert text == "Tool said: Added rice"
    assert calls == [("add_out_of_items", {"items": [{"name": "rice"}]})]

    thread = _recorded(record, "thread")
    assert thread["dynamicTools"] == TOOLS
    assert thread["developerInstructions"] == chatgpt.TOOL_DEVELOPER_INSTRUCTIONS
    assert _recorded(record, "history") == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hi"}]},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hello!"}]},
    ]
    assert _recorded(record, "tool_response") == {
        "id": "codex-1",
        "result": {"contentItems": [{"type": "inputText", "text": "Added rice"}], "success": True},
    }
    assert "outputSchema" not in _recorded(record, "turn")


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_to_the_model_without_details(fake_codex):
    record = fake_codex("tools")

    async def call_tool(name, arguments):
        raise RuntimeError("the database password is hunter2")

    text, _ = await _run(output_schema=None, tools=TOOLS, call_tool=call_tool)

    result = _recorded(record, "tool_response")["result"]
    assert result["success"] is False
    assert "hunter2" not in result["contentItems"][0]["text"]
    assert "hunter2" not in text


@pytest.mark.asyncio
async def test_openai_service_chats_through_codex_with_tools(fake_codex):
    record = fake_codex("tools")
    service, _ = _service()
    seen = []

    async def add(arguments):
        seen.append(arguments)
        return "Added rice to Out of"

    tool = OpenAITool(name="add_out_of_items", description="Add", parameters={"type": "object"}, run=add)
    messages = [
        OpenAIChatMessage("user", "Hi"),
        OpenAIChatMessage("assistant", "Hello!"),
        OpenAIChatMessage("user", "We're out of rice"),
    ]

    reply = await service.chat("Be helpful", messages, [tool], provider=_chatgpt_provider())

    assert reply == "Tool said: Added rice to Out of"
    assert seen == [{"items": [{"name": "rice"}]}]
    assert _recorded(record, "thread")["baseInstructions"] == "Be helpful"
    assert _recorded(record, "thread")["dynamicTools"][0]["inputSchema"] == {"type": "object"}
    assert _recorded(record, "turn")["input"] == [{"type": "text", "text": "We're out of rice"}]
    assert [item["role"] for item in _recorded(record, "history")] == ["user", "assistant"]


def test_to_codex_input_converts_text_and_images():
    content = [
        {"type": "text", "text": "Read this"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
    ]

    assert chatgpt.to_codex_input(content) == [
        {"type": "text", "text": "Read this"},
        {"type": "image", "url": "data:image/jpeg;base64,AAAA"},
    ]


def test_to_codex_input_rejects_audio():
    with pytest.raises(chatgpt.ChatGPTError, match="audio"):
        chatgpt.to_codex_input([{"type": "input_audio", "input_audio": {"data": "", "format": "mp3"}}])


@pytest.mark.asyncio
async def test_device_code_login(fake_codex):
    user_id = uuid4()
    login = await chatgpt.chatgpt_logins.start(user_id)
    try:
        assert login.state == ChatGPTLoginState.waiting
        assert login.user_code == "ABCD-1234"
        assert login.verification_url == "https://auth.openai.com/codex/device"

        for _ in range(100):
            if login.state != ChatGPTLoginState.waiting:
                break
            await asyncio.sleep(0.05)

        assert login.state == ChatGPTLoginState.connected
        assert login.account == "cook@example.com"
        assert login.credential and json.loads(login.credential)["tokens"]["access_token"] == "new"

        # Only the person who started a sign-in can see it
        assert chatgpt.chatgpt_logins.get(login.id, user_id) is login
        assert chatgpt.chatgpt_logins.get(login.id, uuid4()) is None
    finally:
        await chatgpt.chatgpt_logins.discard(login.id)


@pytest.mark.asyncio
async def test_device_code_login_can_be_cancelled(fake_codex):
    record = fake_codex("login_never_finishes")
    user_id = uuid4()

    login = await chatgpt.chatgpt_logins.start(user_id)
    await chatgpt.chatgpt_logins.discard(login.id)

    assert _recorded(record, "cancelled") is True
    assert chatgpt.chatgpt_logins.get(login.id, user_id) is None


@pytest.mark.asyncio
async def test_starting_a_new_login_cancels_the_previous_one(fake_codex):
    fake_codex("login_never_finishes")
    user_id = uuid4()

    first = await chatgpt.chatgpt_logins.start(user_id)
    second = await chatgpt.chatgpt_logins.start(user_id)
    try:
        assert chatgpt.chatgpt_logins.get(first.id, user_id) is None
        assert chatgpt.chatgpt_logins.get(second.id, user_id) is second
    finally:
        await chatgpt.chatgpt_logins.discard(second.id)


def _chatgpt_provider(**overrides) -> AIProviderOut:
    return AIProviderOut(
        id=uuid4(),
        name="ChatGPT",
        provider_type=AIProviderType.chatgpt,
        model="",
        chatgpt_credential=CREDENTIAL,
        **overrides,
    )


def _service() -> tuple[OpenAIService, MagicMock]:
    repos = MagicMock()
    repos.group_ai_provider_settings.get_one.return_value = None
    repos.group_ai_providers.get_chatgpt_credential.return_value = None
    return OpenAIService(repos), repos


@pytest.mark.asyncio
async def test_openai_service_routes_chatgpt_providers_through_codex(fake_codex):
    record = fake_codex()
    service, repos = _service()
    provider = _chatgpt_provider()

    response = await service.get_response("Prompt", "Hi", response_schema=OpenAIText, provider=provider)

    assert response is not None
    assert response.text == "Hi (0 images)"
    # The Pydantic schema goes to Codex in OpenAI's strict form
    assert _recorded(record, "turn")["outputSchema"]["additionalProperties"] is False
    # No model set means Codex picks its default
    assert "model" not in _recorded(record, "thread")

    repos.group_ai_providers.set_chatgpt_credential.assert_called_once()
    provider_id, saved = repos.group_ai_providers.set_chatgpt_credential.call_args.args
    assert provider_id == provider.id
    assert json.loads(saved)["tokens"]["access_token"] == "refreshed"


@pytest.mark.asyncio
async def test_run_chatgpt_turn_searches_the_web_only_when_asked(fake_codex):
    record = fake_codex()

    await _run()
    assert _recorded(record, "thread")["config"]["web_search"] == "disabled"

    await _run(web_search=True)
    thread = _recorded(record, "thread")
    assert thread["config"]["web_search"] == "live"
    assert thread["developerInstructions"] == chatgpt.SEARCH_DEVELOPER_INSTRUCTIONS
    # and nothing else comes on with it
    assert thread["config"]["features"]["shell_tool"] is False
    assert thread["sandbox"] == "read-only"


@pytest.mark.asyncio
async def test_only_chatgpt_providers_search_the_web(fake_codex):
    record = fake_codex()
    service, _ = _service()

    await service.get_response(
        "Prompt", "Hi", response_schema=OpenAIText, provider=_chatgpt_provider(), web_search=True
    )
    assert _recorded(record, "thread")["config"]["web_search"] == "live"

    api_provider = AIProviderOut(id=uuid4(), name="API", provider_type=AIProviderType.openai, model="m", api_key="k")
    with pytest.raises(Exception, match="can't search the web"):
        await service.get_response("Prompt", "Hi", response_schema=OpenAIText, provider=api_provider, web_search=True)


@pytest.mark.asyncio
async def test_openai_service_prefers_the_stored_credential(fake_codex):
    """Another request may have refreshed the tokens since this provider was loaded"""
    fake_codex()
    service, repos = _service()
    repos.group_ai_providers.get_chatgpt_credential.return_value = json.dumps(
        {"auth_mode": "chatgpt", "tokens": {"access_token": "newer"}}
    )

    await service.get_response("Prompt", "Hi", response_schema=OpenAIText, provider=_chatgpt_provider())

    _, saved = repos.group_ai_providers.set_chatgpt_credential.call_args.args
    assert json.loads(saved)["tokens"] == {"access_token": "refreshed"}


@pytest.mark.asyncio
async def test_openai_service_maps_chatgpt_usage_limits_to_rate_limits(fake_codex):
    fake_codex("usage_limit")
    service, _ = _service()

    with pytest.raises(exceptions.RateLimitError):
        await service.get_response("Prompt", "Hi", response_schema=OpenAIText, provider=_chatgpt_provider())


@pytest.mark.asyncio
async def test_test_connection_reports_chatgpt_errors(fake_codex):
    fake_codex("signed_out")
    service, _ = _service()

    result = await service.test_connection(_chatgpt_provider())

    assert result.success is False
    assert result.message and "sign-in" in result.message


def test_chatgpt_providers_dont_need_a_model_or_api_key():
    provider = AIProviderCreate(name="ChatGPT", provider_type=AIProviderType.chatgpt)
    assert provider.model == ""

    with pytest.raises(ValueError, match="model cannot be empty"):
        AIProviderCreate(name="OpenAI", api_key="key")


def test_chatgpt_account_email():
    assert chatgpt_account_email(CREDENTIAL) == "cook@example.com"
    assert chatgpt_account_email(None) is None
    assert chatgpt_account_email("not json") is None
    assert chatgpt_account_email(json.dumps({"tokens": {"id_token": "garbage"}})) is None

    provider = _chatgpt_provider()
    assert provider.chatgpt_account == "cook@example.com"
    # The credential itself is never serialized
    assert "chatgpt_credential" not in provider.model_dump()
    assert "chatgptCredential" not in provider.model_dump(by_alias=True)
