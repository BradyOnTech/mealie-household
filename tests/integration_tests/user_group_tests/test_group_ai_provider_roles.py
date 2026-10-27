"""A provider someone adds takes the jobs no provider has yet, so the first one turns AI on by itself."""

import shutil

from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIProviderCreate, ChatGPTLoginState
from mealie.services.openai.chatgpt import ChatGPTLogin, chatgpt_logins
from tests.unit_tests.services_tests.test_chatgpt_service import CREDENTIAL
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def _settings(client: TestClient, user: TestUser) -> dict:
    response = client.get(api_routes.groups_ai_providers_settings, headers=user.token)
    assert response.status_code == 200
    return response.json()


def _create_api_key_provider(client: TestClient, user: TestUser) -> dict:
    data = {"name": random_string(), "model": "gpt-4o", "apiKey": "test-key"}
    response = client.post(api_routes.groups_ai_providers_providers, json=data, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def _create_chatgpt_provider(client: TestClient, user: TestUser) -> dict:
    login = ChatGPTLogin(user.user_id)
    shutil.rmtree(login._root, ignore_errors=True)
    login.state = ChatGPTLoginState.connected
    login.account = "cook@example.com"
    login.credential = CREDENTIAL
    chatgpt_logins._logins[login.id] = login

    data = {"name": "ChatGPT", "providerType": "chatgpt", "chatgptLoginId": str(login.id)}
    response = client.post(api_routes.groups_ai_providers_providers, json=data, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_first_api_key_provider_becomes_the_default(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    assert _settings(api_client, user)["aiEnabled"] is False

    provider = _create_api_key_provider(api_client, user)

    settings = _settings(api_client, user)
    assert settings["defaultProviderId"] == provider["id"]
    assert settings["aiEnabled"] is True
    # Whether it reads images or audio depends on its model, so those are left for a person to choose
    assert settings["imageProviderId"] is None
    assert settings["audioProviderId"] is None


def test_a_chatgpt_provider_also_reads_images(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    provider = _create_chatgpt_provider(api_client, user)

    settings = _settings(api_client, user)
    assert settings["defaultProviderId"] == provider["id"]
    assert settings["imageProviderId"] == provider["id"]
    # It can't transcribe, so it never becomes the audio provider
    assert settings["audioProviderId"] is None


def test_a_later_provider_leaves_chosen_jobs_alone(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    first = _create_api_key_provider(api_client, user)
    second = _create_chatgpt_provider(api_client, user)

    settings = _settings(api_client, user)
    assert settings["defaultProviderId"] == first["id"]
    # Nobody had the image job yet, so the ChatGPT provider takes it
    assert settings["imageProviderId"] == second["id"]


def test_a_cleared_default_stays_cleared_when_editing(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    provider = _create_api_key_provider(api_client, user)
    cleared = {"defaultProviderId": None, "audioProviderId": None, "imageProviderId": None}
    assert api_client.put(api_routes.groups_ai_providers_settings, json=cleared, headers=user.token).status_code == 200

    response = api_client.put(
        api_routes.groups_ai_providers_providers_provider_id(provider["id"]),
        json={"name": random_string(), "model": "gpt-4o"},
        headers=user.token,
    )
    assert response.status_code == 200

    # Only adding a provider hands out jobs; editing one doesn't undo a person's choice
    assert _settings(api_client, user)["defaultProviderId"] is None


def test_providers_made_in_code_take_no_jobs(unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    user.repos.group_ai_providers.create(AIProviderCreate(name=random_string(), model="gpt-4o", api_key="test-key"))

    settings = user.repos.group_ai_provider_settings.get_one(user.group_id)
    assert settings is not None
    assert settings.default_provider_id is None
