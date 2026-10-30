from __future__ import annotations

import base64
import inspect
import json
import os
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Literal, TypeVar

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from pydantic import BaseModel, field_validator

from mealie.core import exceptions, root_logger
from mealie.core.config import get_app_settings
from mealie.pkgs import img
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.group.ai_providers import (
    AIModelCatalog,
    AIProviderOut,
    AIProviderTestResult,
    AIProviderType,
    AITask,
)
from mealie.schema.openai._base import OpenAIBase
from mealie.schema.openai.general import OpenAIText

from .._base_service import BaseService
from . import chatgpt
from .routing import AIRoute, AIRouteSource, apply_route, resolve_ai_route

T = TypeVar("T", bound=OpenAIBase)
logger = root_logger.get_logger(__name__)

MAX_TOOL_ROUNDS = 8
"""How many times the model can go back to its tools before it has to answer (API-key providers)"""

MODEL_CATALOG_TTL = 10 * 60
MODEL_CATALOG_CACHE_SIZE = 32
_model_catalogs: dict[tuple[Any, str | None], tuple[float, AIModelCatalog]] = {}
"""
Recently listed models, by provider and signed-in account, so opening the settings again doesn't start Codex
again. Only successful listings are kept, and only a few, for a few minutes.
"""


class OpenAINotEnabledException(Exception):
    def __init__(self, message: str = "OpenAI not enabled"):
        self.message = message
        super().__init__(self.message)


class OpenAIDataInjection(BaseModel):
    description: str
    value: str

    @field_validator("value", mode="before")
    def parse_value(cls, value):
        if not value:
            raise ValueError("Value cannot be empty")
        if isinstance(value, str):
            return value

        # convert Pydantic models to JSON
        if isinstance(value, BaseModel):
            return value.model_dump_json()

        # convert Pydantic types to their JSON schema definition
        if inspect.isclass(value) and issubclass(value, BaseModel):
            value = value.model_json_schema()

        # attempt to convert object to JSON
        try:
            return json.dumps(value, separators=(",", ":"))
        except TypeError:
            return value


class OpenAIToolError(Exception):
    """A tool couldn't do what the model asked. The message is handed back to the model."""


@dataclass
class OpenAITool:
    """A function the model may call during `OpenAIService.chat`"""

    name: str
    description: str
    parameters: dict[str, Any]
    """JSON schema for the arguments object"""
    run: Callable[[Any], Awaitable[str]]
    """Takes the arguments the model sent and returns the text to hand back to it"""


@dataclass
class OpenAIChatMessage:
    role: Literal["user", "assistant"]
    content: str


def tool_parameters(model: type[BaseModel]) -> dict[str, Any]:
    """A model's JSON schema with its references inlined and titles dropped, the plainest shape for tools"""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if ref := node.get("$ref"):
                return resolve({**definitions[ref.split("/")[-1]], **{k: v for k, v in node.items() if k != "$ref"}})
            return {key: resolve(value) for key, value in node.items() if key != "title"}
        if isinstance(node, list):
            return [resolve(value) for value in node]
        return node

    return resolve(schema)


class OpenAIAttachment(BaseModel, ABC):
    @abstractmethod
    def build_message(self) -> dict: ...


class OpenAIImageBase(OpenAIAttachment):
    @abstractmethod
    def get_image_url(self) -> str: ...

    def build_message(self) -> dict:
        return {
            "type": "image_url",
            "image_url": {"url": self.get_image_url()},
        }


class OpenAIImageExternal(OpenAIImageBase):
    url: str

    def get_image_url(self) -> str:
        return self.url


class OpenAILocalImage(OpenAIImageBase):
    filename: str
    path: Path

    def get_image_url(self) -> str:
        # Downscale and re-encode at a moderate quality before base64-encoding for the
        # provider. The previous default (quality=100, no resize) inflated typical phone
        # photos well past their original size, exceeding stricter providers' image-size
        # limits (e.g. Anthropic's OpenAI-compatible endpoint rejects images >10MB
        # base64-encoded). Vision models downscale internally, so this loses no accuracy.
        image = img.PillowMinifier.to_jpg(
            self.path,
            dest=self.path.parent.joinpath(f"{self.filename}-min-original.jpg"),
            quality=80,
            max_dimension=2048,
        )
        with open(image, "rb") as f:
            b64content = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64content}"


class OpenAILocalAudio(OpenAIAttachment):
    data: str
    format: str

    def build_message(self) -> dict:
        return {
            "type": "input_audio",
            "input_audio": {"data": self.data, "format": self.format},
        }


class OpenAIService(BaseService):
    PROMPTS_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "prompts"
    TESTING_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "testing"

    def __init__(self, repos: AllRepositories) -> None:
        self.repos = repos
        self.provider_settings = repos.group_ai_provider_settings.get_one(repos.group_id)

        # Load providers
        self.default_provider = (
            self.repos.group_ai_providers.get_one(self.provider_settings.default_provider_id)
            if self.provider_settings and self.provider_settings.default_provider_id
            else None
        )
        self.audio_provider = (
            self.repos.group_ai_providers.get_one(self.provider_settings.audio_provider_id)
            if self.provider_settings and self.provider_settings.audio_provider_id
            else None
        )
        self.image_provider = (
            self.repos.group_ai_providers.get_one(self.provider_settings.image_provider_id)
            if self.provider_settings and self.provider_settings.image_provider_id
            else None
        )

        self._providers: dict[Any, AIProviderOut | None] = {
            provider.id: provider
            for provider in (self.default_provider, self.audio_provider, self.image_provider)
            if provider
        }

        # Build client
        settings = get_app_settings()
        self.custom_prompt_dir = settings.OPENAI_CUSTOM_PROMPT_DIR

        super().__init__()

    def _load_provider(self, provider_id: Any) -> AIProviderOut | None:
        # The repository is scoped to this group, so another group's provider is never found
        if provider_id not in self._providers:
            self._providers[provider_id] = self.repos.group_ai_providers.get_one(provider_id)
        return self._providers[provider_id]

    def route(self, task: AITask | None, *, images: bool = False) -> AIRoute | None:
        """Which provider, model and reasoning effort a task runs on (see `routing`), or None if there's none"""
        return resolve_ai_route(self.provider_settings, task, images=images)

    def can_search_web(self, task: AITask) -> bool:
        """
        Whether the task's provider can search the web. ChatGPT providers can, through Codex's own search;
        API-key providers' endpoints differ too much to rely on.
        """
        settings = self.provider_settings
        if not (settings and settings.ai_enabled):
            return False
        route = self.route(task)
        provider = self._load_provider(route.provider_id) if route else None
        return bool(provider and provider.provider_type == AIProviderType.chatgpt)

    def can_read_images(self, task: AITask) -> bool:
        """Whether the task has a provider to read images with, so images can be sent to it at all"""
        settings = self.provider_settings
        if not (settings and settings.ai_enabled):
            return False
        route = self.route(task, images=True)
        return bool(route and self._load_provider(route.provider_id))

    def provider_for(self, task: AITask | None, *, images: bool = False) -> AIProviderOut:
        """The provider a task's request runs on, with the model and reasoning effort chosen for it"""
        route = self.route(task, images=images)
        if route is None:
            raise OpenAINotEnabledException("No image provider set" if images else "No default provider set")

        provider = self._load_provider(route.provider_id)
        if provider is None:
            # Never quietly swap in another provider (or account) for the one that was chosen
            what = (
                "image provider"
                if route.source in (AIRouteSource.task_images, AIRouteSource.group_images)
                else "provider"
            )
            raise OpenAINotEnabledException(f"The {what} chosen for this task no longer exists")
        return apply_route(provider, route)

    def get_client(self, provider: AIProviderOut) -> AsyncOpenAI:
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            base_url=provider.base_url or None,
            api_key=provider.api_key,
            timeout=provider.timeout,
            default_headers=provider.request_headers or None,
            default_query=provider.request_params or None,
        )

    async def ping(
        self, provider: AIProviderOut, message: str, images: list[OpenAILocalImage] | None = None
    ) -> OpenAIText | None:
        """Send a one-off chat message to a provider. Shared by the admin debug endpoint and test_connection."""
        prompt = self.get_prompt("general.debug")
        return await self.get_response(
            prompt, message, response_schema=OpenAIText, attachments=images, provider=provider
        )

    async def test_connection(self, provider: AIProviderOut) -> AIProviderTestResult:
        """
        Confirm a provider's base_url/api_key/model actually work by sending a real chat message,
        rather than just listing models - a provider can pass a /models check and still fail to
        complete a request (see discussion #8051).

        If that succeeds, additionally report whether the provider can read an image, so someone
        setting one up learns at config time that it can't be used as the image provider, rather
        than when a recipe-from-image import fails later. That's reported as capability info, not
        as a failure: a text-only provider is a perfectly valid setup.
        """
        try:
            response = await self.ping(provider, "Hello, checking to see if I can reach you.")
        except Exception as e:
            # Report the error type/status only, never the provider's response body: this route is
            # open to group managers, who could otherwise point base_url at an internal host and
            # read its error pages back through the test result. The full error is logged instead,
            # where it's only visible to whoever runs the server.
            self.logger.exception("AI provider connection test failed")
            cause = e.__cause__ or e
            if isinstance(cause, chatgpt.ChatGPTError):
                # These come from Codex, not from a user-supplied URL, so they're safe to show
                return AIProviderTestResult(success=False, message=str(cause))

            status = getattr(cause, "status_code", None)
            name = type(cause).__name__
            return AIProviderTestResult(success=False, message=f"{name} (HTTP {status})" if status else name)

        if not response:
            return AIProviderTestResult(success=False, message="No response received from the provider.")

        return AIProviderTestResult(success=True, supports_images=await self._check_image_support(provider))

    async def _check_image_support(self, provider: AIProviderOut) -> bool:
        """
        Best-effort check of whether this provider can actually read an image, by sending it a
        bundled screenshot of a short recipe (see `testing/`) and looking for that recipe in the
        reply. Advisory only - a provider that can't do this is still perfectly usable for
        everything except the image provider role.
        """
        from mealie.core.dependencies.dependencies import get_temporary_path

        try:
            with get_temporary_path() as temp_path:
                image_path = temp_path / "recipe-image.jpg"
                shutil.copy(self.TESTING_DIR / "recipe-image.jpg", image_path)

                response = await self.ping(
                    provider,
                    "Read the attached image and reply in English with the recipe title exactly as written in it.",
                    images=[OpenAILocalImage(filename=image_path.name, path=image_path)],
                )
        except Exception:
            return False

        if not response:
            return False

        keywords = json.loads((self.TESTING_DIR / "recipe.json").read_text())["test_keywords"]
        return any(keyword.lower() in response.text.lower() for keyword in keywords)

    def _get_provider(
        self, attachments: list[OpenAIAttachment] | None = None, task: AITask | None = None
    ) -> AIProviderOut:
        """Select the provider for a task's request based on attachment types (see `routing`)."""
        has_image = any(isinstance(a, OpenAIImageBase) for a in (attachments or []))
        has_audio = any(isinstance(a, OpenAILocalAudio) for a in (attachments or []))

        if has_image and has_audio:
            raise ValueError("Cannot process both images and audio in one request")

        if has_audio:
            if not self.audio_provider:
                raise OpenAINotEnabledException("No audio provider set")
            return self.audio_provider

        return self.provider_for(task, images=has_image)

    def _get_prompt_file_candidates(self, name: str) -> list[Path]:
        """
        Returns a list of prompt file path candidates.
        First optional entry is the users custom prompt file, if configured and existing,
        second one (or only one) is the systems default prompt file
        """
        tree = name.split(".")
        relative_path = Path(*tree[:-1], tree[-1] + ".txt")

        default_prompt_file = (self.PROMPTS_DIR / relative_path).resolve()
        if not default_prompt_file.is_relative_to(self.PROMPTS_DIR.resolve()):
            raise ValueError(f"Invalid prompt name '{name}': resolves outside prompts directory")

        try:
            # Only include custom files if the custom_dir is configured, is a directory, and the prompt file exists
            custom_dir = Path(self.custom_prompt_dir).resolve() if self.custom_prompt_dir else None
            if custom_dir and not custom_dir.is_dir():
                custom_dir = None
        except Exception:
            custom_dir = None

        if custom_dir:
            custom_prompt_file = (custom_dir / relative_path).resolve()
            if not custom_prompt_file.is_relative_to(custom_dir):
                logger.warning(f"Custom prompt file resolves outside custom dir, skipping: {custom_prompt_file}")
            elif custom_prompt_file.exists():
                logger.debug(f"Found valid custom prompt file: {custom_prompt_file}")
                return [custom_prompt_file, default_prompt_file]
            else:
                logger.debug(f"Custom prompt file doesn't exist: {custom_prompt_file}")
        else:
            logger.debug(f"Custom prompt dir doesn't exist: {custom_dir}")

        # Otherwise, only return the default internal prompt file
        return [default_prompt_file]

    def _load_prompt_from_file(self, name: str) -> str:
        """Attempts to load custom prompt, otherwise falling back to the default"""
        prompt_file_candidates = self._get_prompt_file_candidates(name)
        content = None
        last_error = None
        for prompt_file in prompt_file_candidates:
            try:
                logger.debug(f"Trying to load prompt file: {prompt_file}")
                with open(prompt_file) as f:
                    content = f.read()
                    if content:
                        logger.debug(f"Successfully read prompt from {prompt_file}")
                        break
            except OSError as e:
                last_error = e

        if not content:
            if last_error:
                raise OSError(f"Unable to load prompt {name}") from last_error
            else:
                # This handles the case where the list was empty (no existing candidates found)
                attempted_paths = ", ".join(map(str, prompt_file_candidates))
                raise OSError(f"Unable to load prompt '{name}'. No valid content found in files: {attempted_paths}")

        return content

    def get_prompt(self, name: str, data_injections: list[OpenAIDataInjection] | None = None) -> str:
        """
        Load stored prompt and inject data into it.

        Access prompts with dot notation.
        For example, to access `prompts/recipes/parse-recipe-ingredients.txt`, use
        `recipes.parse-recipe-ingredients`
        """

        if not name:
            raise ValueError("Prompt name cannot be empty")

        content = self._load_prompt_from_file(name)

        if not data_injections:
            return content

        content_parts = [content]
        for data_injection in data_injections:
            content_parts.append(
                dedent(
                    f"""
                    ###
                    {data_injection.description}
                    ---

                    {data_injection.value}
                    """
                )
            )
        return "\n".join(content_parts)

    async def _get_raw_response(
        self,
        prompt: str,
        content: list[dict],
        response_schema: type[T],
        provider: AIProviderOut,
        web_search: bool = False,
    ) -> T | None:
        import openai
        from openai.types.chat import ChatCompletion

        if provider.provider_type == AIProviderType.chatgpt:
            return await self._get_chatgpt_response(prompt, content, response_schema, provider, web_search)
        if web_search:
            raise exceptions.OpenAIServiceError("This AI provider can't search the web")

        client = self.get_client(provider)
        # parse() builds the same response_format payload create() would send, but its
        # client-side validation runs as a post_parser that the raw-response path never
        # triggers, so we read the body ourselves and let parse_openai_response() below
        # do the parsing (e.g. of markdown-fenced JSON the SDK would otherwise discard).
        async with client.chat.completions.with_streaming_response.parse(
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
            model=provider.model,
            response_format=response_schema,
            **self._reasoning_kwargs(provider),
        ) as response:
            completion = ChatCompletion.model_validate(json.loads(await response.text()))

        for choice in completion.choices:
            if choice.finish_reason == "length":
                raise openai.LengthFinishReasonError(completion=completion)
            if choice.finish_reason == "content_filter":
                raise openai.ContentFilterFinishReasonError()

        if not completion.choices:
            return None

        return response_schema.parse_openai_response(completion.choices[0].message.content)

    @staticmethod
    def _reasoning_kwargs(provider: AIProviderOut) -> dict[str, Any]:
        """
        Chat Completions' `reasoning_effort`, only when one was chosen: plenty of OpenAI-compatible endpoints and
        models reject the parameter, so a provider nobody set it for sends exactly what it always has.
        """
        return {"reasoning_effort": provider.reasoning_effort} if provider.reasoning_effort else {}

    async def _get_chatgpt_response(
        self,
        prompt: str,
        content: list[dict],
        response_schema: type[T],
        provider: AIProviderOut,
        web_search: bool = False,
    ) -> T | None:
        from openai.lib._pydantic import to_strict_json_schema

        inputs = chatgpt.to_codex_input(content)
        async with chatgpt.credential_lock(provider.id):
            text = await chatgpt.run_chatgpt_turn(
                self._load_chatgpt_credential(provider),
                instructions=prompt,
                inputs=inputs,
                # The same strict schema the Chat Completions path sends as its response_format
                output_schema=to_strict_json_schema(response_schema),
                model=provider.model or None,
                effort=provider.reasoning_effort,
                timeout=provider.timeout,
                save_credential=lambda credential: self._save_chatgpt_credential(provider, credential),
                web_search=web_search,
            )

        return response_schema.parse_openai_response(text)

    def _load_chatgpt_credential(self, provider: AIProviderOut) -> str:
        # Read it fresh rather than trusting `provider`: another request may have refreshed the
        # tokens since that was loaded. A provider being tested before it's saved has the id of
        # the sign-in it's using.
        if login := chatgpt.chatgpt_logins.find(provider.id):
            credential = login.credential
        else:
            stored = self.repos.group_ai_providers.get_chatgpt_credential(provider.id)
            credential = stored or provider.chatgpt_credential

        if not credential:
            raise chatgpt.ChatGPTAuthError("This provider isn't signed in to ChatGPT")
        return credential

    def _save_chatgpt_credential(self, provider: AIProviderOut, credential: str) -> None:
        if login := chatgpt.chatgpt_logins.find(provider.id):
            login.credential = credential
        else:
            self.repos.group_ai_providers.set_chatgpt_credential(provider.id, credential)

    async def get_response(
        self,
        prompt: str,
        message: str,
        *,
        response_schema: type[T],
        attachments: list[OpenAIAttachment] | None = None,
        provider: AIProviderOut | None = None,
        task: AITask | None = None,
        web_search: bool = False,
    ) -> T | None:
        """
        Send data to OpenAI and return the response message content. `task` picks the provider, model and
        reasoning effort chosen for it; without one, the group's default (or image) provider is used.
        `web_search` lets the model search the web, which only ChatGPT providers can (see `can_search_web`).
        """
        import openai

        try:
            provider = provider or self._get_provider(attachments, task)
            user_messages: list[dict] = [{"type": "text", "text": message}]
            for attachment in attachments or []:
                user_messages.append(attachment.build_message())

            return await self._get_raw_response(prompt, user_messages, response_schema, provider, web_search)
        except (openai.RateLimitError, chatgpt.ChatGPTUsageLimitError) as e:
            raise exceptions.RateLimitError(str(e)) from e
        except Exception as e:
            raise Exception(f"OpenAI Request Failed. {e.__class__.__name__}: {e}") from e

    async def chat(
        self,
        instructions: str,
        messages: Sequence[OpenAIChatMessage],
        tools: Sequence[OpenAITool],
        *,
        provider: AIProviderOut | None = None,
        task: AITask | None = None,
    ) -> str:
        """
        Reply to the last of `messages`, a user's, with the rest as the conversation so far. The
        model can call any of `tools`, as often as it needs to, before it answers.
        """
        import openai

        if not messages or messages[-1].role != "user":
            raise ValueError("A chat has to end with the user's message")

        provider = provider or self._get_provider(task=task)
        by_name = {tool.name: tool for tool in tools}

        async def call_tool(name: str, arguments: Any) -> tuple[bool, str]:
            tool = by_name.get(name)
            if tool is None:
                return False, f"There's no tool called {name}."
            try:
                return True, await tool.run(arguments)
            except OpenAIToolError as e:
                return False, str(e)
            except Exception:
                self.logger.exception(f"AI tool {name} failed")
                return False, "That didn't work because of an error in Mealie."

        try:
            if provider.provider_type == AIProviderType.chatgpt:
                return await self._chat_with_chatgpt(instructions, messages, tools, call_tool, provider)
            return await self._chat_with_completions(instructions, messages, tools, call_tool, provider)
        except (openai.RateLimitError, chatgpt.ChatGPTUsageLimitError) as e:
            raise exceptions.RateLimitError(str(e)) from e

    async def _chat_with_completions(
        self,
        instructions: str,
        messages: Sequence[OpenAIChatMessage],
        tools: Sequence[OpenAITool],
        call_tool: chatgpt.ToolHandler,
        provider: AIProviderOut,
    ) -> str:
        client = self.get_client(provider)
        conversation: list[Any] = [{"role": "system", "content": instructions}]
        conversation += [{"role": message.role, "content": message.content} for message in messages]
        specs: list[Any] = [
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
            }
            for tool in tools
        ]

        for _ in range(MAX_TOOL_ROUNDS):
            completion = await client.chat.completions.create(
                model=provider.model, messages=conversation, tools=specs, **self._reasoning_kwargs(provider)
            )
            if not completion.choices:
                raise exceptions.OpenAIServiceError("The AI provider didn't reply")

            reply = completion.choices[0].message
            calls = [call for call in reply.tool_calls or [] if call.type == "function"]
            if not calls:
                return (reply.content or "").strip()

            conversation.append(
                {"role": "assistant", "content": reply.content, "tool_calls": [call.model_dump() for call in calls]}
            )
            for call in calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except ValueError:
                    success, text = False, "The arguments weren't valid JSON."
                else:
                    success, text = await call_tool(call.function.name, arguments)
                conversation.append({"role": "tool", "tool_call_id": call.id, "content": text})

        raise exceptions.OpenAIServiceError("The AI provider kept calling tools without answering")

    async def _chat_with_chatgpt(
        self,
        instructions: str,
        messages: Sequence[OpenAIChatMessage],
        tools: Sequence[OpenAITool],
        call_tool: chatgpt.ToolHandler,
        provider: AIProviderOut,
    ) -> str:
        *earlier, latest = messages
        specs = [
            {"type": "function", "name": tool.name, "description": tool.description, "inputSchema": tool.parameters}
            for tool in tools
        ]
        async with chatgpt.credential_lock(provider.id):
            return await chatgpt.run_chatgpt_turn(
                self._load_chatgpt_credential(provider),
                instructions=instructions,
                inputs=[{"type": "text", "text": latest.content}],
                output_schema=None,
                model=provider.model or None,
                effort=provider.reasoning_effort,
                timeout=provider.timeout,
                save_credential=lambda credential: self._save_chatgpt_credential(provider, credential),
                tools=specs,
                call_tool=call_tool,
                history=[chatgpt.to_codex_history(message.role, message.content) for message in earlier],
            )

    async def list_models(
        self, provider: AIProviderOut, *, account: str | None = None, refresh: bool = False
    ) -> AIModelCatalog:
        """
        The models a ChatGPT provider's catalog lists, for picking one. Never fails: when the models can't be
        listed, the catalog says so and a model name can still be typed in. API-key providers aren't asked, since
        their endpoints differ in what (if anything) they list, and Mealie doesn't call user-supplied URLs here.

        `account` is the signed-in account, which keeps one account's catalog from being shown for another.
        """
        if provider.provider_type != AIProviderType.chatgpt:
            return AIModelCatalog(discovered=False, message="Type the model name your provider's documentation gives.")

        key = (provider.id, account or provider.chatgpt_account)
        now = time.monotonic()
        cached = _model_catalogs.get(key)
        if cached and not refresh and now - cached[0] < MODEL_CATALOG_TTL:
            return cached[1]

        try:
            async with chatgpt.credential_lock(provider.id):
                models = await chatgpt.list_chatgpt_models(
                    self._load_chatgpt_credential(provider),
                    save_credential=lambda credential: self._save_chatgpt_credential(provider, credential),
                )
        except chatgpt.ChatGPTError as e:
            return AIModelCatalog(discovered=False, message=str(e))
        except Exception:
            self.logger.exception("Failed to list ChatGPT models")
            return AIModelCatalog(discovered=False, message="The models couldn't be listed.")

        catalog = AIModelCatalog(discovered=True, models=models)
        for stale in [k for k, (at, _) in _model_catalogs.items() if now - at >= MODEL_CATALOG_TTL]:
            del _model_catalogs[stale]
        _model_catalogs[key] = (now, catalog)
        while len(_model_catalogs) > MODEL_CATALOG_CACHE_SIZE:
            del _model_catalogs[next(iter(_model_catalogs))]
        return catalog

    async def transcribe_audio(self, audio_file_path: Path) -> str | None:
        import openai

        if not self.audio_provider:
            raise OpenAINotEnabledException("No audio provider set")
        if self.audio_provider.provider_type == AIProviderType.chatgpt:
            raise OpenAINotEnabledException("ChatGPT subscription providers can't transcribe audio")

        client = self.get_client(self.audio_provider)

        # Create a transcription from the audio
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model=self.audio_provider.model,
                    file=audio_file,
                )
            return transcript.text
        except openai.RateLimitError as e:
            raise exceptions.RateLimitError(str(e)) from e
        except Exception as e:
            self.logger.warning(
                f"Failed to create audio transcription, falling back to chat completion ({e.__class__.__name__}: {e})"
            )

        # Fallback to chat completion
        path_obj = Path(audio_file_path)
        with open(path_obj, "rb") as audio_file:
            audio_data = base64.b64encode(audio_file.read()).decode("utf-8")

        file_ext = path_obj.suffix.lstrip(".").lower()
        audio_attachment = OpenAILocalAudio(data=audio_data, format=file_ext)
        response = await self.get_response(
            self.get_prompt("general.transcribe-audio"),
            "Attached is the audio data.",
            response_schema=OpenAIText,
            attachments=[audio_attachment],
        )

        return response.text if response else None
