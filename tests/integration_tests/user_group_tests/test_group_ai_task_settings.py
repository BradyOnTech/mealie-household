"""Per-task AI choices and provider reasoning effort, through the group settings API"""

import shutil
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIModelOption, AIProviderCreate, ChatGPTLoginState
from mealie.services.openai import chatgpt
from mealie.services.openai import openai as openai_module
from mealie.services.openai.chatgpt import ChatGPTLogin, chatgpt_logins
from tests.unit_tests.services_tests.test_chatgpt_service import CREDENTIAL
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


@pytest.fixture(autouse=True)
def _empty_catalog_cache(monkeypatch):
    monkeypatch.setattr(openai_module, "_model_catalogs", {})


def _settings(client: TestClient, user: TestUser) -> dict:
    response = client.get(api_routes.groups_ai_providers_settings, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def _put_settings(client: TestClient, user: TestUser, payload: dict):
    return client.put(api_routes.groups_ai_providers_settings, json=payload, headers=user.token)


def _create_provider(client: TestClient, user: TestUser, **extra) -> dict:
    data = {"name": random_string(), "model": "gpt-api", "apiKey": "test-key", **extra}
    response = client.post(api_routes.groups_ai_providers_providers, json=data, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def _create_provider_in_repo(user: TestUser) -> dict:
    """For users the fixtures don't let manage their group"""
    provider = user.repos.group_ai_providers.create(AIProviderCreate(name=random_string(), model="m", api_key="k"))
    return {"id": str(provider.id)}


def _allow_managing(user: TestUser) -> None:
    db_user = user.repos.users.get_one(user.user_id)
    assert db_user
    db_user.can_manage = True
    user.repos.users.update(db_user.id, db_user)


def _connected_login(user: TestUser) -> ChatGPTLogin:
    login = ChatGPTLogin(user.user_id)
    shutil.rmtree(login._root, ignore_errors=True)
    login.state = ChatGPTLoginState.connected
    login.account = "cook@example.com"
    login.credential = CREDENTIAL
    chatgpt_logins._logins[login.id] = login
    return login


def _roles(settings: dict) -> dict:
    return {key: settings[key] for key in ("defaultProviderId", "audioProviderId", "imageProviderId")}


# =======================================================================
# Saving task choices


def test_task_choices_are_saved_and_returned(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    default = _create_provider(api_client, user)
    vision = _create_provider(api_client, user, model="gpt-vision")
    settings = _settings(api_client, user)
    assert settings["taskSettings"] == []

    payload = {
        **_roles(settings),
        "taskSettings": [
            {"task": "recipe_building", "providerId": vision["id"], "model": " gpt-big ", "reasoningEffort": "HIGH"},
            {"task": "cookbook_extraction", "imageProviderId": vision["id"], "imageReasoningEffort": "medium"},
            # Nothing chosen, so it isn't kept
            {"task": "ingredient_parsing"},
        ],
    }
    response = _put_settings(api_client, user, payload)
    assert response.status_code == 200, response.text

    saved = {setting["task"]: setting for setting in _settings(api_client, user)["taskSettings"]}
    assert set(saved) == {"recipe_building", "cookbook_extraction"}
    assert saved["recipe_building"]["model"] == "gpt-big"
    assert saved["recipe_building"]["reasoningEffort"] == "high"
    assert saved["cookbook_extraction"]["imageProviderId"] == vision["id"]
    assert saved["cookbook_extraction"]["providerId"] is None
    assert _settings(api_client, user)["defaultProviderId"] == default["id"]
    # No group image provider, but extraction can read images with its own
    assert _settings(api_client, user)["imageReadingTasks"] == ["cookbook_extraction"]

    # Sending the list again replaces it
    response = _put_settings(api_client, user, {**payload, "taskSettings": []})
    assert response.status_code == 200
    assert _settings(api_client, user)["taskSettings"] == []


def test_an_old_client_leaves_task_choices_alone(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    provider = _create_provider(api_client, user)
    settings = _settings(api_client, user)
    choice = {"task": "household_assistant", "providerId": provider["id"], "reasoningEffort": "low"}
    assert _put_settings(api_client, user, {**_roles(settings), "taskSettings": [choice]}).status_code == 200

    # A client from before task choices existed only sends the three roles
    response = _put_settings(api_client, user, {**_roles(settings), "imageProviderId": provider["id"]})
    assert response.status_code == 200, response.text

    after = _settings(api_client, user)
    assert after["imageProviderId"] == provider["id"]
    assert [setting["task"] for setting in after["taskSettings"]] == ["household_assistant"]


@pytest.mark.parametrize(
    "task_settings",
    [
        # a model or effort only means something with the provider it's for
        [{"task": "recipe_building", "model": "gpt-big"}],
        [{"task": "recipe_building", "reasoningEffort": "high"}],
        [{"task": "cookbook_discovery", "imageModel": "gpt-vision"}],
        # text-only tasks have no image provider
        [{"task": "ingredient_parsing", "imageProviderId": "{provider}"}],
        [
            {"task": "recipe_building", "providerId": "{provider}"},
            {"task": "recipe_building", "providerId": "{provider}"},
        ],
        [{"task": "recipe_building", "providerId": "{provider}", "reasoningEffort": "very high; drop table"}],
        [{"task": "not_a_task", "providerId": "{provider}"}],
    ],
)
def test_invalid_task_choices_are_refused(
    api_client: TestClient, unique_user_fn_scoped: TestUser, task_settings: list[dict]
):
    user = unique_user_fn_scoped
    provider = _create_provider(api_client, user)
    settings = _settings(api_client, user)
    for setting in task_settings:
        for key, value in setting.items():
            if value == "{provider}":
                setting[key] = provider["id"]

    response = _put_settings(api_client, user, {**_roles(settings), "taskSettings": task_settings})
    assert response.status_code == 422, response.text
    assert _settings(api_client, user)["taskSettings"] == []


def test_deleting_a_provider_removes_the_choices_made_for_it(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    default = _create_provider(api_client, user)
    other = _create_provider(api_client, user)
    payload = {
        **_roles(_settings(api_client, user)),
        "taskSettings": [
            {"task": "recipe_building", "providerId": other["id"], "model": "gpt-big"},
            {
                "task": "cookbook_discovery",
                "providerId": default["id"],
                "imageProviderId": other["id"],
                "imageModel": "x",
            },
        ],
    }
    assert _put_settings(api_client, user, payload).status_code == 200

    response = api_client.delete(api_routes.groups_ai_providers_providers_provider_id(other["id"]), headers=user.token)
    assert response.status_code == 200

    remaining = _settings(api_client, user)["taskSettings"]
    assert remaining == [
        {
            "task": "cookbook_discovery",
            "providerId": default["id"],
            "model": None,
            "reasoningEffort": None,
            "imageProviderId": None,
            "imageModel": None,
            "imageReasoningEffort": None,
        }
    ]


# =======================================================================
# Group isolation


def test_settings_cant_use_another_groups_provider(
    api_client: TestClient, unique_user_fn_scoped: TestUser, g2_user: TestUser
):
    user = unique_user_fn_scoped
    mine = _create_provider(api_client, user)
    theirs = _create_provider_in_repo(g2_user)
    roles = _roles(_settings(api_client, user))

    for payload in [
        {**roles, "defaultProviderId": theirs["id"]},
        {**roles, "imageProviderId": theirs["id"]},
        {**roles, "taskSettings": [{"task": "recipe_building", "providerId": theirs["id"]}]},
        {**roles, "taskSettings": [{"task": "cookbook_discovery", "imageProviderId": theirs["id"]}]},
        {**roles, "taskSettings": [{"task": "recipe_building", "providerId": str(uuid4())}]},
    ]:
        response = _put_settings(api_client, user, payload)
        assert response.status_code == 400, payload

    settings = _settings(api_client, user)
    assert settings["defaultProviderId"] == mine["id"]
    assert settings["taskSettings"] == []


def test_admin_updates_check_the_target_group_and_keep_task_choices(
    api_client: TestClient, admin_user: TestUser, unique_user_fn_scoped: TestUser, g2_user: TestUser
):
    user = unique_user_fn_scoped
    mine = _create_provider(api_client, user)
    theirs = _create_provider_in_repo(g2_user)
    roles = _roles(_settings(api_client, user))
    choice = {"task": "recipe_translation", "providerId": mine["id"]}
    assert _put_settings(api_client, user, {**roles, "taskSettings": [choice]}).status_code == 200

    def admin_put(ai_settings: dict):
        return api_client.put(
            api_routes.admin_groups_item_id(user.group_id),
            json={"id": user.group_id, "name": user.group_id, "aiProviderSettings": ai_settings},
            headers=admin_user.token,
        )

    # Another group's provider is refused here too
    assert admin_put({**roles, "defaultProviderId": theirs["id"]}).status_code == 400

    # Leaving taskSettings out keeps them
    response = admin_put({**roles, "imageProviderId": mine["id"]})
    assert response.status_code == 200, response.text
    assert [s["task"] for s in response.json()["aiProviderSettings"]["taskSettings"]] == ["recipe_translation"]


def test_models_of_another_groups_provider_are_not_found(
    api_client: TestClient, unique_user_fn_scoped: TestUser, g2_user: TestUser
):
    theirs = _create_provider_in_repo(g2_user)
    response = api_client.get(
        api_routes.groups_ai_providers_providers_provider_id_models(theirs["id"]), headers=unique_user_fn_scoped.token
    )
    assert response.status_code == 404


def test_models_need_can_manage(api_client: TestClient, user_tuple: list[TestUser]):
    usr, _ = user_tuple
    provider = _create_provider_in_repo(usr)
    user = usr.repos.users.get_one(usr.user_id)
    assert user
    user.can_manage = False
    usr.repos.users.update(user.id, user)

    response = api_client.get(
        api_routes.groups_ai_providers_providers_provider_id_models(provider["id"]), headers=usr.token
    )
    assert response.status_code == 403


# =======================================================================
# Listing models


def test_an_api_key_provider_has_no_catalog(api_client: TestClient, unique_user_fn_scoped: TestUser):
    provider = _create_provider(api_client, unique_user_fn_scoped, baseUrl="http://127.0.0.1:1")
    response = api_client.get(
        api_routes.groups_ai_providers_providers_provider_id_models(provider["id"]),
        headers=unique_user_fn_scoped.token,
    )
    assert response.status_code == 200
    assert response.json()["discovered"] is False
    assert response.json()["models"] == []


def test_a_chatgpt_provider_lists_its_models(api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch):
    user = unique_user_fn_scoped
    login = _connected_login(user)
    response = api_client.post(
        api_routes.groups_ai_providers_providers,
        json={"name": "ChatGPT", "providerType": "chatgpt", "chatgptLoginId": str(login.id)},
        headers=user.token,
    )
    provider = response.json()
    seen: list[str] = []

    async def fake_list(credential, *, save_credential):
        seen.append(credential)
        return [AIModelOption(model="fast-model", display_name="Fast", is_default=True)]

    monkeypatch.setattr(chatgpt, "list_chatgpt_models", fake_list)

    response = api_client.get(
        api_routes.groups_ai_providers_providers_provider_id_models(provider["id"]), headers=user.token
    )
    assert response.status_code == 200, response.text
    assert response.json()["discovered"] is True
    assert response.json()["models"][0]["model"] == "fast-model"
    # It used the provider's own sign-in
    assert seen == [CREDENTIAL]


def test_a_pending_sign_in_lists_models_only_for_whoever_started_it(
    api_client: TestClient, user_tuple: list[TestUser], monkeypatch
):
    owner, other = user_tuple
    _allow_managing(owner)
    _allow_managing(other)
    login = _connected_login(owner)

    async def fake_list(credential, *, save_credential):
        return [AIModelOption(model="fast-model", display_name="Fast")]

    monkeypatch.setattr(chatgpt, "list_chatgpt_models", fake_list)
    try:
        route = api_routes.groups_ai_providers_chatgpt_login_login_id_models(login.id)
        # Someone else in the same group can't use it
        assert api_client.get(route, headers=other.token).status_code == 404

        response = api_client.get(route, headers=owner.token)
        assert response.status_code == 200
        assert response.json()["models"][0]["model"] == "fast-model"

        login.state = ChatGPTLoginState.waiting
        login.credential = None
        response = api_client.get(route, headers=owner.token)
        assert response.status_code == 200
        assert response.json()["discovered"] is False
    finally:
        chatgpt_logins.forget(login.id)


# =======================================================================
# A provider's reasoning effort


def test_provider_reasoning_effort_survives_old_clients(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    provider = _create_provider(api_client, user, reasoningEffort="medium")
    assert provider["reasoningEffort"] == "medium"
    route = api_routes.groups_ai_providers_providers_provider_id(provider["id"])

    # An old client sends everything it knows about, which doesn't include the effort
    response = api_client.put(route, json={"name": provider["name"], "model": "gpt-newer"}, headers=user.token)
    assert response.status_code == 200, response.text
    assert response.json()["reasoningEffort"] == "medium"
    assert response.json()["model"] == "gpt-newer"

    # A new client can clear it
    response = api_client.put(
        route, json={"name": provider["name"], "model": "gpt-newer", "reasoningEffort": None}, headers=user.token
    )
    assert response.json()["reasoningEffort"] is None

    summary = next(p for p in _settings(api_client, user)["providers"] if p["id"] == provider["id"])
    assert summary["model"] == "gpt-newer"
    assert "apiKey" not in summary


def test_provider_reasoning_effort_is_validated(api_client: TestClient, unique_user_fn_scoped: TestUser):
    data = {"name": random_string(), "model": "gpt-api", "apiKey": "k", "reasoningEffort": "<script>"}
    response = api_client.post(api_routes.groups_ai_providers_providers, json=data, headers=unique_user_fn_scoped.token)
    assert response.status_code == 422
