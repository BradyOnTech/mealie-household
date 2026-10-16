"""
ChatGPT subscription support, through the Codex CLI's app-server.

Codex app-server is a JSON-RPC agent runtime (spoken to over stdio) that can sign in to a
ChatGPT account and bill requests to that account's plan instead of to an API key. Mealie uses
it in two ways:

* Device-code sign-in. Whoever sets up the provider enters a short code on OpenAI's site, from
  any device, so this works on a headless server with nothing redirecting back to Mealie. See
  `ChatGPTLoginManager`.
* One isolated, ephemeral Codex thread per request. The stored credential (Codex's `auth.json`)
  is written to a fresh temporary CODEX_HOME for the call, and whatever Codex leaves there
  afterwards is handed back to be saved, since Codex rotates the tokens as they age. See
  `run_chatgpt_turn`.

OpenAI still marks the app-server protocol experimental, so the Docker image pins the Codex
version this was written against.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import tempfile
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from mealie.core import root_logger
from mealie.core.config import get_app_settings
from mealie.core.settings.static import APP_VERSION
from mealie.schema.group.ai_providers import (
    AIProviderCreate,
    AIProviderType,
    AIProviderUpdate,
    ChatGPTLoginOut,
    ChatGPTLoginState,
    chatgpt_account_email,
)
from mealie.schema.response import ErrorResponse

logger = root_logger.get_logger(__name__)

# Turn off everything a one-shot extraction request doesn't need (tools, connectors, plugins,
# memory), both so the model can't wander off and so each throwaway app-server starts faster.
CODEX_CONFIG: dict[str, Any] = {
    "web_search": "disabled",
    "features": {
        "apps": False,
        "browser_use": False,
        "computer_use": False,
        "goals": False,
        "hooks": False,
        "image_generation": False,
        "memories": False,
        "multi_agent": False,
        "plugins": False,
        "remote_plugin": False,
        "shell_tool": False,
        "skill_search": False,
        "sleep_tool": False,
        "tool_suggest": False,
        "unified_exec": False,
        "view_image": False,
    },
    # Leave out the prompt sections about skills, sandboxing and apps, none of which Mealie uses
    "skills": {"include_instructions": False},
    "include_permissions_instructions": False,
    "include_apps_instructions": False,
}
DEVELOPER_INSTRUCTIONS = (
    "Answer directly from the content you're given. Don't run commands, read files, or browse the web."
)
TOOL_DEVELOPER_INSTRUCTIONS = (
    "The tools you're given are how you see and change the household's data, so use them rather than guessing. "
    "Don't run commands, read files, or browse the web."
)
REASONING_EFFORT = "low"
"""Mealie's requests are extraction and formatting, which don't benefit from long reasoning"""

ToolHandler = Callable[[str, Any], Awaitable[tuple[bool, str]]]
"""Runs a tool Mealie offered the model: given the tool's name and arguments, returns whether it
worked and the text to hand back to the model"""

RPC_TIMEOUT = 60
LOGIN_TIMEOUT = 15 * 60
"""How long a device code stays valid"""
FINISHED_LOGIN_TTL = 60 * 60
"""How long a finished sign-in is kept in memory, waiting to be saved to a provider"""
STDOUT_LIMIT = 64 * 1024 * 1024
"""Codex echoes each request back as a notification, base64 images included"""

_PASSTHROUGH_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class ChatGPTError(Exception):
    """A request through a ChatGPT subscription failed. Messages are safe to show to the user."""

    def as_http_error(self) -> HTTPException:
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(message=str(self)))


class ChatGPTAuthError(ChatGPTError):
    """The provider's ChatGPT sign-in is missing or no longer valid"""


class ChatGPTUsageLimitError(ChatGPTError):
    """The ChatGPT plan's usage limit was reached"""


class _AppServer:
    """One `codex app-server` process with its own CODEX_HOME, spoken to over JSON-RPC on stdio"""

    def __init__(self, root: Path) -> None:
        self.home = root / "home"
        self.cwd = root / "work"
        self.on_notification: Callable[[str, dict[str, Any]], None] | None = None
        self.on_request: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = None
        """Answers a request from Codex, or returns None to turn it down"""

        self._process: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._waiters: list[asyncio.Future[dict[str, Any]]] = []
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._stderr: deque[str] = deque(maxlen=20)
        self._closing = False

    async def start(self) -> None:
        codex_bin = get_app_settings().CODEX_BIN
        executable = codex_bin if Path(codex_bin).is_absolute() else shutil.which(codex_bin)
        if not executable or not Path(executable).is_file():
            raise ChatGPTError(
                "The Codex CLI isn't installed on this server, so ChatGPT subscription providers can't be used. "
                "Install it, or set CODEX_BIN to its path."
            )

        self.home.mkdir(parents=True, exist_ok=True)
        self.cwd.mkdir(parents=True, exist_ok=True)

        # Only what Codex needs: Mealie's environment holds secrets Codex has no business seeing
        env = {key: value for key in _PASSTHROUGH_ENV if (value := os.environ.get(key)) is not None}
        env |= {"HOME": str(self.home.parent), "CODEX_HOME": str(self.home), "CODEX_SQLITE_HOME": str(self.home)}

        self._process = await asyncio.create_subprocess_exec(
            executable,
            "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=env,
            limit=STDOUT_LIMIT,
        )
        self._tasks = [asyncio.create_task(self._read_stdout()), asyncio.create_task(self._read_stderr())]

        await self.request(
            "initialize",
            {
                "clientInfo": {"name": "mealie", "title": "Mealie", "version": APP_VERSION},
                "capabilities": {"experimentalApi": True},
            },
        )
        await self._send({"method": "initialized", "params": {}})

    def new_waiter(self) -> asyncio.Future[dict[str, Any]]:
        """A future for a notification handler to resolve, which fails instead if Codex exits first"""
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        return future

    async def request(self, method: str, params: dict[str, Any], timeout: float = RPC_TIMEOUT) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._send({"method": method, "id": request_id, "params": params})
            response = await asyncio.wait_for(future, timeout)
        except TimeoutError as e:
            raise ChatGPTError(f"Codex didn't answer {method} in time") from e
        finally:
            self._pending.pop(request_id, None)

        if error := response.get("error"):
            message = error.get("message") if isinstance(error, dict) else error
            raise ChatGPTError(f"Codex couldn't {method}: {message}")

        result = response.get("result")
        return result if isinstance(result, dict) else {}

    async def close(self) -> None:
        self._closing = True
        process, self._process = self._process, None
        if process and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # A waiter can fail (Codex exited) before anything awaited it; mark those as seen so
        # asyncio doesn't log them as unhandled
        for future in self._waiters:
            if future.done() and not future.cancelled():
                future.exception()

    async def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or not process.stdin or process.returncode is not None:
            raise ChatGPTError("Codex isn't running")

        async with self._write_lock:
            process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        stdout = self._process.stdout
        try:
            while line := await stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    await self._dispatch(message)
        except ValueError, ConnectionError:
            logger.exception("Lost the connection to Codex app-server")
        finally:
            self._fail_waiters()

    async def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = _as_dict(message.get("params"))

        if not method:
            future = self._pending.get(request_id) if isinstance(request_id, int) else None
            if future and not future.done():
                future.set_result(message)
        elif request_id is not None:
            # Codex asks the client things like approvals and tool results. Mealie answers calls to
            # the tools it offered, and turns everything else down, approvals included.
            result = None
            if self.on_request:
                try:
                    result = await self.on_request(method, params)
                except Exception:
                    logger.exception(f"Failed to answer Codex's {method} request")
            with contextlib.suppress(ChatGPTError):
                if result is None:
                    await self._send({"id": request_id, "error": {"code": -32601, "message": f"Unsupported: {method}"}})
                else:
                    await self._send({"id": request_id, "result": result})
        elif self.on_notification:
            self.on_notification(method, params)

    async def _read_stderr(self) -> None:
        assert self._process and self._process.stderr
        stderr = self._process.stderr
        with contextlib.suppress(ValueError):
            while line := await stderr.readline():
                if text := _ANSI_ESCAPE.sub("", line.decode(errors="replace")).strip():
                    self._stderr.append(text)

    def _fail_waiters(self) -> None:
        futures = [*self._pending.values(), *self._waiters]
        if self._closing:
            for future in futures:
                future.cancel()
            return

        if self._stderr:
            logger.warning("Codex app-server exited unexpectedly:\n" + "\n".join(self._stderr))
        for future in futures:
            if not future.done():
                future.set_exception(ChatGPTError("Codex stopped unexpectedly"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_credential(credential: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(credential)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _read_credential(path: Path) -> str | None:
    """Codex's auth.json, if it's there and valid"""
    try:
        credential = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return credential if _parse_credential(credential) else None


def _write_credential(path: Path, credential: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(credential)


def _turn_error(turn: dict[str, Any]) -> ChatGPTError:
    error = _as_dict(turn.get("error"))
    message = str(error.get("message") or f"ChatGPT request ended with status {turn.get('status')}")
    match error.get("codexErrorInfo"):
        case "usageLimitExceeded" | "rateLimitExceeded":
            return ChatGPTUsageLimitError(message)
        case "unauthorized":
            return ChatGPTAuthError(f"{message} Sign in to ChatGPT again in this provider's settings.")
        case _:
            return ChatGPTError(message)


def to_codex_input(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a Chat Completions user message's content parts to Codex turn input"""
    inputs: list[dict[str, Any]] = []
    for part in content:
        match part.get("type"):
            case "text":
                inputs.append({"type": "text", "text": part["text"]})
            case "image_url":
                inputs.append({"type": "image", "url": part["image_url"]["url"]})
            case _:
                raise ChatGPTError("ChatGPT subscription providers can only read text and images, not audio")
    return inputs


def to_codex_history(role: str, text: str) -> dict[str, Any]:
    """An earlier chat message, as the Responses API item Codex keeps in a thread's history"""
    if role == "assistant":
        return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


async def run_chatgpt_turn(
    credential: str,
    *,
    instructions: str,
    inputs: list[dict[str, Any]],
    output_schema: dict[str, Any] | None,
    model: str | None,
    timeout: float,
    save_credential: Callable[[str], None],
    tools: list[dict[str, Any]] | None = None,
    call_tool: ToolHandler | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """
    Run one request through a throwaway Codex thread, signed in with `credential`, and return the
    reply's text.

    `tools` are offered to the model as Codex dynamic tools (`{"type": "function", "name": ...,
    "description": ..., "inputSchema": ...}`), and each call the model makes is run with
    `call_tool`. `history` is the conversation so far, from `to_codex_history`, put ahead of
    `inputs`.

    `save_credential` is called with Codex's auth.json afterwards if Codex changed it, which it
    does when it refreshes the tokens. That happens even when the request itself fails, since
    the old refresh token stops working as soon as it's been used.
    """
    root = Path(tempfile.mkdtemp(prefix="mealie-chatgpt-"))
    server = _AppServer(root)
    auth_path = server.home / "auth.json"
    server.home.mkdir(parents=True)
    _write_credential(auth_path, credential)

    turn_done = server.new_waiter()
    agent_messages: list[dict[str, Any]] = []

    def on_notification(method: str, params: dict[str, Any]) -> None:
        if method == "item/completed":
            item = params.get("item")
            if isinstance(item, dict) and item.get("type") == "agentMessage":
                agent_messages.append(item)
        elif method == "turn/completed" and not turn_done.done():
            turn_done.set_result(params)

    async def on_request(method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method != "item/tool/call" or not call_tool:
            return None
        try:
            success, text = await call_tool(str(params.get("tool") or ""), params.get("arguments"))
        except Exception:
            logger.exception("A tool offered to ChatGPT failed")
            success, text = False, "That didn't work because of an error in Mealie."
        return {"contentItems": [{"type": "inputText", "text": text}], "success": success}

    server.on_notification = on_notification
    server.on_request = on_request
    try:
        await server.start()

        account = (await server.request("account/read", {"refreshToken": False})).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            raise ChatGPTAuthError("This provider's ChatGPT sign-in is no longer valid. Sign in to ChatGPT again.")

        thread_params: dict[str, Any] = {
            "cwd": str(server.cwd),
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "ephemeral": True,
            "baseInstructions": instructions,
            "developerInstructions": TOOL_DEVELOPER_INSTRUCTIONS if tools else DEVELOPER_INSTRUCTIONS,
            "config": CODEX_CONFIG,
        }
        if model:
            thread_params["model"] = model
        if tools:
            thread_params["dynamicTools"] = tools
        thread = await server.request("thread/start", thread_params)
        thread_id = (thread.get("thread") or {}).get("id")
        if not thread_id:
            raise ChatGPTError("Codex didn't start a thread")
        if history:
            await server.request("thread/inject_items", {"threadId": thread_id, "items": history})

        turn_params: dict[str, Any] = {"threadId": thread_id, "input": inputs, "effort": REASONING_EFFORT}
        if output_schema:
            turn_params["outputSchema"] = output_schema
        await server.request("turn/start", turn_params)

        try:
            completed = await asyncio.wait_for(turn_done, timeout or None)
        except TimeoutError as e:
            raise ChatGPTError(f"ChatGPT didn't finish within {timeout} seconds") from e

        turn = _as_dict(completed.get("turn"))
        if turn.get("status") != "completed":
            raise _turn_error(turn)

        # Prefer the final answer over any commentary the model gave along the way
        messages = [i for i in turn.get("items") or [] if isinstance(i, dict) and i.get("type") == "agentMessage"]
        messages = messages or agent_messages
        final = [m for m in messages if m.get("phase") == "final_answer"] or messages
        text = str(final[-1].get("text") or "").strip() if final else ""
        if not text:
            raise ChatGPTError("ChatGPT finished without replying")

        return text
    finally:
        await server.close()
        refreshed = _read_credential(auth_path)
        if refreshed and _parse_credential(refreshed) != _parse_credential(credential):
            try:
                save_credential(refreshed)
            except Exception:
                logger.exception("Failed to save the refreshed ChatGPT credential")
        shutil.rmtree(root, ignore_errors=True)


_credential_locks: dict[UUID, asyncio.Lock] = {}


def credential_lock(key: UUID) -> asyncio.Lock:
    """
    Requests through the same ChatGPT sign-in have to take turns: when Codex refreshes the tokens
    during one request, the refresh token any concurrent request started with stops working.
    """
    return _credential_locks.setdefault(key, asyncio.Lock())


class ChatGPTLogin:
    """One device-code sign-in, from asking Codex for a code until the user finishes (or doesn't)"""

    def __init__(self, user_id: UUID) -> None:
        self.id = uuid4()
        self.user_id = user_id
        self.state = ChatGPTLoginState.waiting
        self.verification_url: str | None = None
        self.user_code: str | None = None
        self.account: str | None = None
        self.error: str | None = None
        self.credential: str | None = None
        self.finished_at: float | None = None

        self._root = Path(tempfile.mkdtemp(prefix="mealie-chatgpt-login-"))
        self._server = _AppServer(self._root)
        self._codex_login_id: str | None = None
        self._watcher: asyncio.Task[None] | None = None

    def out(self) -> ChatGPTLoginOut:
        return ChatGPTLoginOut(
            id=self.id,
            state=self.state,
            verification_url=self.verification_url,
            user_code=self.user_code,
            account=self.account,
            error=self.error,
        )

    async def start(self) -> None:
        completed = self._server.new_waiter()
        account_saved = asyncio.Event()

        def on_notification(method: str, params: dict[str, Any]) -> None:
            if method == "account/login/completed" and not completed.done():
                completed.set_result(params)
            elif method == "account/updated" and params.get("authMode") == "chatgpt":
                account_saved.set()

        self._server.on_notification = on_notification
        try:
            await self._server.start()
            result = await self._server.request("account/login/start", {"type": "chatgptDeviceCode"})
            self._codex_login_id = result.get("loginId")
            self.verification_url = result.get("verificationUrl")
            self.user_code = result.get("userCode")
            if not (self._codex_login_id and self.verification_url and self.user_code):
                raise ChatGPTError("Codex didn't return a sign-in code")
        except BaseException:
            completed.cancel()
            await self._cleanup()
            raise

        self._watcher = asyncio.create_task(self._watch(completed, account_saved))

    async def _watch(self, completed: asyncio.Future[dict[str, Any]], account_saved: asyncio.Event) -> None:
        try:
            result = await asyncio.wait_for(completed, LOGIN_TIMEOUT)
            if not result.get("success"):
                raise ChatGPTError(str(result.get("error") or "The ChatGPT sign-in wasn't completed"))

            # Codex announces the finished sign-in a moment before it has saved the account
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(account_saved.wait(), 10)

            account = (await self._server.request("account/read", {"refreshToken": False})).get("account")
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                raise ChatGPTError("The ChatGPT sign-in finished without an account")

            credential = _read_credential(self._server.home / "auth.json")
            if not credential:
                raise ChatGPTError("Codex didn't save the ChatGPT sign-in")

            self.credential = credential
            self.account = account.get("email") or chatgpt_account_email(credential)
            self.state = ChatGPTLoginState.connected
        except TimeoutError:
            self.state = ChatGPTLoginState.expired
            self.error = "The sign-in code expired. Start again to get a new one."
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"ChatGPT sign-in failed: {e}")
            self.state = ChatGPTLoginState.failed
            self.error = str(e) if isinstance(e, ChatGPTError) else "The ChatGPT sign-in failed"
        finally:
            self.finished_at = time.monotonic()
            await self._cleanup()

    async def cancel(self) -> None:
        if self.state == ChatGPTLoginState.waiting and self._codex_login_id:
            with contextlib.suppress(ChatGPTError):
                await self._server.request("account/login/cancel", {"loginId": self._codex_login_id}, timeout=5)

        if self._watcher and not self._watcher.done():
            self._watcher.cancel()
            await asyncio.gather(self._watcher, return_exceptions=True)

        self.credential = None
        await self._cleanup()

    async def _cleanup(self) -> None:
        await self._server.close()
        shutil.rmtree(self._root, ignore_errors=True)


class ChatGPTLoginManager:
    """
    Sign-ins that are in progress, or finished and waiting to be saved to a provider.

    These only live in this process's memory. Mealie runs a single worker by default; with more,
    a sign-in has to be checked on by the same worker that started it.
    """

    def __init__(self) -> None:
        self._logins: dict[UUID, ChatGPTLogin] = {}

    async def start(self, user_id: UUID) -> ChatGPTLogin:
        await self._prune()

        # One sign-in per person at a time, so abandoned ones don't leave Codex processes behind
        for login in [login for login in self._logins.values() if login.user_id == user_id]:
            await self.discard(login.id)

        login = ChatGPTLogin(user_id)
        await login.start()
        self._logins[login.id] = login
        return login

    def get(self, login_id: UUID, user_id: UUID) -> ChatGPTLogin | None:
        login = self._logins.get(login_id)
        return login if login and login.user_id == user_id else None

    def find(self, login_id: UUID) -> ChatGPTLogin | None:
        """Look up a sign-in by id alone, for a provider that's being tested with one before it's saved"""
        return self._logins.get(login_id)

    def forget(self, login_id: UUID) -> None:
        """Drop a finished sign-in, once its credential has been saved to a provider"""
        if login := self._logins.pop(login_id, None):
            login.credential = None

    async def discard(self, login_id: UUID) -> None:
        if login := self._logins.pop(login_id, None):
            await login.cancel()

    async def _prune(self) -> None:
        now = time.monotonic()
        for login in list(self._logins.values()):
            if login.finished_at is not None and now - login.finished_at > FINISHED_LOGIN_TTL:
                await self.discard(login.id)


chatgpt_logins = ChatGPTLoginManager()


class _AIProviderWithCredential(AIProviderUpdate):
    chatgpt_credential: str


def attach_chatgpt_credential(data: AIProviderCreate, user_id: UUID) -> AIProviderCreate:
    """
    Swap the finished sign-in a ChatGPT provider names (`chatgpt_login_id`) for the credential it
    produced, ready to be saved. Anything else is returned as it is.
    """
    if data.provider_type != AIProviderType.chatgpt or not data.chatgpt_login_id:
        return data

    login = chatgpt_logins.get(data.chatgpt_login_id, user_id)
    if not login or not login.credential:
        raise ChatGPTAuthError("That ChatGPT sign-in has expired. Sign in again.")

    return _AIProviderWithCredential.model_validate({**data.model_dump(), "chatgpt_credential": login.credential})
