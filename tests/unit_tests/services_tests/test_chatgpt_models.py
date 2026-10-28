"""Listing a ChatGPT provider's models through `model/list`, against a fake `codex app-server`"""

import json
import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from mealie.schema.group.ai_providers import AIProviderOut, AIProviderType
from mealie.services.openai import chatgpt
from mealie.services.openai import openai as openai_module
from mealie.services.openai.openai import OpenAIService
from tests.unit_tests.services_tests.test_chatgpt_service import CREDENTIAL, _recorded, fake_codex  # noqa: F401


@pytest.fixture(autouse=True)
def _empty_catalog_cache(monkeypatch):
    monkeypatch.setattr(openai_module, "_model_catalogs", {})


def _provider() -> AIProviderOut:
    return AIProviderOut(
        id=uuid4(), name="ChatGPT", provider_type=AIProviderType.chatgpt, model="", chatgpt_credential=CREDENTIAL
    )


def _service() -> tuple[OpenAIService, MagicMock]:
    repos = MagicMock()
    repos.group_ai_provider_settings.get_one.return_value = None
    repos.group_ai_providers.get_chatgpt_credential.return_value = None
    return OpenAIService(repos), repos


@pytest.mark.asyncio
async def test_lists_every_page_of_visible_models(fake_codex):  # noqa: F811
    record = fake_codex()

    models = await chatgpt.list_chatgpt_models(CREDENTIAL, save_credential=lambda _: None)

    # Hidden, malformed and repeated entries are left out
    assert [m.model for m in models] == ["fast-model", "deep-model"]
    fast, deep = models
    assert fast.display_name == "Fast"
    assert fast.is_default is True
    assert fast.default_reasoning_effort == "low"
    assert [(e.effort, e.description) for e in fast.supported_reasoning_efforts] == [
        ("low", "Quickest"),
        ("medium", "Balanced"),
    ]
    assert fast.input_modalities == ["text", "image"]
    # A model that doesn't say what it reads is taken to read text and images, as Codex documents
    assert deep.input_modalities == ["text", "image"]
    assert deep.description is None

    calls = _recorded(record, "model_list")
    assert calls[0] == {"limit": chatgpt.MODEL_LIST_PAGE_SIZE, "includeHidden": False}
    assert calls[1]["cursor"] == "page-2"


@pytest.mark.asyncio
async def test_stops_paging_after_a_bounded_number_of_pages(fake_codex):  # noqa: F811
    record = fake_codex("endless_models")

    assert await chatgpt.list_chatgpt_models(CREDENTIAL, save_credential=lambda _: None) == []
    assert len(_recorded(record, "model_list")) == chatgpt.MODEL_LIST_MAX_PAGES


@pytest.mark.asyncio
async def test_listing_needs_a_valid_sign_in(fake_codex):  # noqa: F811
    fake_codex("signed_out")

    with pytest.raises(chatgpt.ChatGPTAuthError):
        await chatgpt.list_chatgpt_models(CREDENTIAL, save_credential=lambda _: None)


@pytest.mark.asyncio
async def test_listing_cleans_up_its_codex_home(fake_codex, monkeypatch):  # noqa: F811
    fake_codex()
    roots: list[str] = []
    real_mkdtemp = chatgpt.tempfile.mkdtemp

    def mkdtemp(**kwargs):
        roots.append(real_mkdtemp(**kwargs))
        return roots[-1]

    monkeypatch.setattr(chatgpt.tempfile, "mkdtemp", mkdtemp)

    await chatgpt.list_chatgpt_models(CREDENTIAL, save_credential=lambda _: None)

    assert roots
    assert not any(os.path.exists(root) for root in roots)


def test_parse_model_option_ignores_unknown_and_bad_fields():
    option = chatgpt.parse_model_option(
        {
            "model": "m",
            "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": ""}, "junk", {"x": 1}],
            "inputModalities": ["text", 3],
            "defaultReasoningEffort": 5,
            "brandNewField": True,
        }
    )
    assert option is not None
    assert option.display_name == "m"
    assert [e.effort for e in option.supported_reasoning_efforts] == ["low"]
    assert option.input_modalities == ["text"]
    assert option.default_reasoning_effort is None

    assert chatgpt.parse_model_option({"model": "m", "hidden": True}) is None
    assert chatgpt.parse_model_option({"model": "  "}) is None


@pytest.mark.asyncio
async def test_service_lists_models_and_caches_them(fake_codex):  # noqa: F811
    record = fake_codex()
    service, _ = _service()
    provider = _provider()

    catalog = await service.list_models(provider)
    again = await service.list_models(provider)

    assert catalog.discovered is True
    assert [m.model for m in catalog.models] == ["fast-model", "deep-model"]
    assert again == catalog
    # Two pages, listed once
    assert len(_recorded(record, "model_list")) == 2

    await service.list_models(provider, refresh=True)
    assert len(_recorded(record, "model_list")) == 4


@pytest.mark.asyncio
async def test_service_reports_a_failed_listing_without_raising(fake_codex):  # noqa: F811
    fake_codex("signed_out")
    service, _ = _service()

    catalog = await service.list_models(_provider())

    assert catalog.discovered is False
    assert catalog.models == []
    assert "Sign in to ChatGPT again" in (catalog.message or "")
    # Failures aren't cached, so fixing the sign-in shows the models straight away
    assert openai_module._model_catalogs == {}


@pytest.mark.asyncio
async def test_api_key_providers_are_never_asked_for_models(monkeypatch):
    service, _ = _service()

    async def fail(*args, **kwargs):
        raise AssertionError("an API-key provider's URL must not be called")

    monkeypatch.setattr(chatgpt, "list_chatgpt_models", fail)
    provider = AIProviderOut(id=uuid4(), name="OpenAI", api_key="key", model="gpt-api", base_url="http://internal")

    catalog = await service.list_models(provider)
    assert catalog.discovered is False


@pytest.mark.asyncio
async def test_listing_saves_refreshed_tokens(fake_codex, monkeypatch):  # noqa: F811
    """Codex may refresh the tokens while listing, and the old refresh token stops working once it has"""
    fake_codex()
    service, repos = _service()
    provider = _provider()

    async def list_and_refresh(credential, *, save_credential):
        save_credential(json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "refreshed"}}))
        return []

    monkeypatch.setattr(chatgpt, "list_chatgpt_models", list_and_refresh)
    await service.list_models(provider)

    provider_id, saved = repos.group_ai_providers.set_chatgpt_credential.call_args.args
    assert provider_id == provider.id
    assert json.loads(saved)["tokens"]["access_token"] == "refreshed"
