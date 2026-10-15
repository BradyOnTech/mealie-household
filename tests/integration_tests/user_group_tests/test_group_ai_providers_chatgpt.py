"""
Integration tests for ChatGPT subscription AI providers: saving one from a finished sign-in,
keeping its credential private, and keeping it out of the audio provider role.

Sign-ins are put straight into the in-memory login manager, so Codex never runs.
"""

import json
import shutil
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIProviderType, ChatGPTLoginState
from mealie.services.openai import OpenAIService
from mealie.services.openai.chatgpt import ChatGPTLogin, chatgpt_logins
from tests.unit_tests.services_tests.test_chatgpt_service import CREDENTIAL
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _connected_login(user: TestUser) -> ChatGPTLogin:
    login = ChatGPTLogin(user.user_id)
    shutil.rmtree(login._root, ignore_errors=True)
    login.state = ChatGPTLoginState.connected
    login.account = "cook@example.com"
    login.credential = CREDENTIAL
    chatgpt_logins._logins[login.id] = login
    return login


@pytest.fixture()
def login(unique_user: TestUser) -> Generator[ChatGPTLogin]:
    login = _connected_login(unique_user)
    yield login
    chatgpt_logins.forget(login.id)


def _set_can_manage(user: TestUser, can_manage: bool) -> None:
    user_model = user.repos.users.get_one(user.user_id)
    assert user_model
    user_model.can_manage = can_manage
    user.repos.users.update(user_model.id, user_model)


def _create_chatgpt_provider(user: TestUser) -> str:
    provider = user.repos.group_ai_providers.create(
        {
            "name": random_string(),
            "provider_type": AIProviderType.chatgpt,
            "model": "",
            "chatgpt_credential": CREDENTIAL,
        }
    )
    return str(provider.id)


def test_create_chatgpt_provider_requires_a_sign_in(api_client: TestClient, unique_user: TestUser):
    data = {"name": random_string(), "providerType": "chatgpt"}
    response = api_client.post(api_routes.groups_ai_providers_providers, json=data, headers=unique_user.token)
    assert response.status_code == 400


def test_create_chatgpt_provider_from_a_sign_in(api_client: TestClient, unique_user: TestUser, login: ChatGPTLogin):
    data = {"name": random_string(), "providerType": "chatgpt", "chatgptLoginId": str(login.id)}
    response = api_client.post(api_routes.groups_ai_providers_providers, json=data, headers=unique_user.token)
    assert response.status_code == 200

    provider = response.json()
    try:
        assert provider["providerType"] == "chatgpt"
        assert provider["model"] == ""
        assert provider["chatgptAccount"] == "cook@example.com"
        assert "chatgptCredential" not in provider
        assert CREDENTIAL not in response.text

        stored = unique_user.repos.group_ai_providers.get_chatgpt_credential(provider["id"])
        assert stored == CREDENTIAL

        # The sign-in now lives on the provider, so it's dropped from memory
        assert chatgpt_logins.get(login.id, unique_user.user_id) is None
    finally:
        route = api_routes.groups_ai_providers_providers_provider_id(provider["id"])
        api_client.delete(route, headers=unique_user.token)


def test_create_chatgpt_provider_from_someone_elses_sign_in(api_client: TestClient, user_tuple: list[TestUser]):
    owner, other = user_tuple
    _set_can_manage(other, True)
    login = _connected_login(owner)
    try:
        data = {"name": random_string(), "providerType": "chatgpt", "chatgptLoginId": str(login.id)}
        response = api_client.post(api_routes.groups_ai_providers_providers, json=data, headers=other.token)
        assert response.status_code == 400
    finally:
        chatgpt_logins.forget(login.id)


def test_update_chatgpt_provider_keeps_its_sign_in(api_client: TestClient, unique_user: TestUser):
    provider_id = _create_chatgpt_provider(unique_user)
    try:
        response = api_client.put(
            api_routes.groups_ai_providers_providers_provider_id(provider_id),
            json={"name": random_string(), "providerType": "chatgpt", "model": "gpt-test"},
            headers=unique_user.token,
        )
        assert response.status_code == 200
        assert response.json()["model"] == "gpt-test"
        assert unique_user.repos.group_ai_providers.get_chatgpt_credential(provider_id) == CREDENTIAL
    finally:
        api_client.delete(api_routes.groups_ai_providers_providers_provider_id(provider_id), headers=unique_user.token)


def test_update_chatgpt_provider_with_a_new_sign_in(api_client: TestClient, unique_user: TestUser, login: ChatGPTLogin):
    provider_id = _create_chatgpt_provider(unique_user)
    new_credential = json.dumps({"tokens": {"access_token": "someone else"}})
    login.credential = new_credential
    try:
        response = api_client.put(
            api_routes.groups_ai_providers_providers_provider_id(provider_id),
            json={"name": random_string(), "providerType": "chatgpt", "chatgptLoginId": str(login.id)},
            headers=unique_user.token,
        )
        assert response.status_code == 200
        assert unique_user.repos.group_ai_providers.get_chatgpt_credential(provider_id) == new_credential
    finally:
        api_client.delete(api_routes.groups_ai_providers_providers_provider_id(provider_id), headers=unique_user.token)


def test_chatgpt_provider_cant_be_the_audio_provider(api_client: TestClient, unique_user: TestUser):
    provider_id = _create_chatgpt_provider(unique_user)
    try:
        update = {"defaultProviderId": provider_id, "audioProviderId": provider_id, "imageProviderId": provider_id}
        response = api_client.put(api_routes.groups_ai_providers_settings, json=update, headers=unique_user.token)
        assert response.status_code == 400

        update["audioProviderId"] = None
        response = api_client.put(api_routes.groups_ai_providers_settings, json=update, headers=unique_user.token)
        assert response.status_code == 200
        settings = response.json()
        assert settings["defaultProviderId"] == provider_id
        assert settings["imageProviderId"] == provider_id
        assert settings["providers"][0]["providerType"] == "chatgpt"
    finally:
        api_client.delete(api_routes.groups_ai_providers_providers_provider_id(provider_id), headers=unique_user.token)


def test_chatgpt_login_status_is_private_to_its_owner(api_client: TestClient, user_tuple: list[TestUser]):
    owner, other = user_tuple
    _set_can_manage(owner, True)
    _set_can_manage(other, True)
    login = _connected_login(owner)
    try:
        route = api_routes.groups_ai_providers_chatgpt_login_login_id(login.id)

        response = api_client.get(route, headers=owner.token)
        assert response.status_code == 200
        assert response.json() == {
            "id": str(login.id),
            "state": "connected",
            "verificationUrl": None,
            "userCode": None,
            "account": "cook@example.com",
            "error": None,
        }

        assert api_client.get(route, headers=other.token).status_code == 404
        assert api_client.delete(route, headers=other.token).status_code == 404

        assert api_client.delete(route, headers=owner.token).status_code == 200
        assert api_client.get(route, headers=owner.token).status_code == 404
    finally:
        chatgpt_logins.forget(login.id)


def test_chatgpt_login_routes_require_can_manage(api_client: TestClient, user_tuple: list[TestUser]):
    usr, _ = user_tuple
    _set_can_manage(usr, False)

    response = api_client.post(api_routes.groups_ai_providers_chatgpt_login, headers=usr.token)
    assert response.status_code == 403


def test_test_unsaved_chatgpt_provider_needs_a_sign_in(api_client: TestClient, unique_user: TestUser):
    data = {"name": random_string(), "providerType": "chatgpt"}
    response = api_client.post(api_routes.groups_ai_providers_providers_test, json=data, headers=unique_user.token)
    assert response.status_code == 200
    assert response.json()["success"] is False


def test_test_unsaved_chatgpt_provider_uses_its_sign_in(
    api_client: TestClient, unique_user: TestUser, login: ChatGPTLogin, monkeypatch
):
    tested = []

    async def _fake_test_connection(self, provider):
        tested.append(provider)
        return {"success": True}

    monkeypatch.setattr(OpenAIService, "test_connection", _fake_test_connection)

    data = {"name": random_string(), "providerType": "chatgpt", "chatgptLoginId": str(login.id)}
    response = api_client.post(api_routes.groups_ai_providers_providers_test, json=data, headers=unique_user.token)
    assert response.status_code == 200

    (provider,) = tested
    # The service finds the sign-in (and saves any refreshed tokens to it) by this id
    assert provider.id == login.id
    assert provider.chatgpt_credential == CREDENTIAL
    # Testing doesn't use up the sign-in
    assert chatgpt_logins.get(login.id, unique_user.user_id) is login


def test_test_saved_chatgpt_provider_with_a_new_sign_in(
    api_client: TestClient, unique_user: TestUser, login: ChatGPTLogin, monkeypatch
):
    provider_id = _create_chatgpt_provider(unique_user)
    tested = []

    async def _fake_test_connection(self, provider):
        tested.append(provider)
        return {"success": True}

    monkeypatch.setattr(OpenAIService, "test_connection", _fake_test_connection)
    try:
        overrides = {"name": random_string(), "providerType": "chatgpt", "chatgptLoginId": str(login.id)}
        response = api_client.post(
            api_routes.groups_ai_providers_providers_provider_id_test(provider_id),
            json=overrides,
            headers=unique_user.token,
        )
        assert response.status_code == 200
        assert tested[0].id == login.id

        # Without a new sign-in, the saved one is used
        overrides.pop("chatgptLoginId")
        response = api_client.post(
            api_routes.groups_ai_providers_providers_provider_id_test(provider_id),
            json=overrides,
            headers=unique_user.token,
        )
        assert response.status_code == 200
        assert str(tested[1].id) == provider_id
        assert tested[1].chatgpt_credential == CREDENTIAL
    finally:
        api_client.delete(api_routes.groups_ai_providers_providers_provider_id(provider_id), headers=unique_user.token)


def test_switching_a_chatgpt_provider_to_an_api_key_drops_its_sign_in(api_client: TestClient, unique_user: TestUser):
    provider_id = _create_chatgpt_provider(unique_user)
    try:
        # An API-key provider needs a key
        update = {"name": random_string(), "providerType": "openai", "model": "gpt-4o"}
        response = api_client.put(
            api_routes.groups_ai_providers_providers_provider_id(provider_id), json=update, headers=unique_user.token
        )
        assert response.status_code == 400

        response = api_client.put(
            api_routes.groups_ai_providers_providers_provider_id(provider_id),
            json=update | {"apiKey": "key"},
            headers=unique_user.token,
        )
        assert response.status_code == 200
        assert response.json()["chatgptAccount"] is None
        assert unique_user.repos.group_ai_providers.get_chatgpt_credential(provider_id) is None
    finally:
        api_client.delete(api_routes.groups_ai_providers_providers_provider_id(provider_id), headers=unique_user.token)


def test_unknown_chatgpt_login(api_client: TestClient, unique_user: TestUser):
    route = api_routes.groups_ai_providers_chatgpt_login_login_id(uuid4())
    assert api_client.get(route, headers=unique_user.token).status_code == 404
