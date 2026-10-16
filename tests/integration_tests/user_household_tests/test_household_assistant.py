"""The household assistant's chat endpoint, with a scripted model calling its real tools"""

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIProviderSettingsUpdate, AIProviderType
from mealie.schema.recipe.recipe import Recipe
from mealie.services.household_services import assistant, groceries
from mealie.services.openai.openai import OpenAIService
from tests.unit_tests.services_tests.test_openai_chat import ScriptedCompletions, call, completion
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

CHAT = "/api/households/assistant/chat"
RESTOCK = "/api/households/groceries/restock"


def user_says(*messages: str) -> dict[str, Any]:
    roles = ["user", "assistant"]
    return {"messages": [{"role": roles[i % 2], "content": text} for i, text in enumerate(messages)]}


@pytest.fixture
def assistant_user(unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch) -> TestUser:
    user = unique_user_fn_scoped
    provider = user.repos.group_ai_providers.create(
        {"name": random_string(), "provider_type": AIProviderType.openai, "model": "gpt-test", "api_key": "test"}
    )
    user.repos.group_ai_provider_settings.update(
        user.group_id,
        AIProviderSettingsUpdate(default_provider_id=provider.id, audio_provider_id=None, image_provider_id=None),
    )
    for module in (groceries, assistant):
        monkeypatch.setattr(module, "household_today", lambda: date(2026, 10, 14))
    return user


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch):
    """Script the model's replies for the next chat"""
    script = ScriptedCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=script))
    monkeypatch.setattr(OpenAIService, "get_client", lambda self, provider: client)

    def reply(*replies):
        script.replies = list(replies)
        return script

    return reply


def tool_results(script: ScriptedCompletions, request: int = 1) -> list[Any]:
    return [
        json.loads(message["content"]) if message["content"].startswith("{") else message["content"]
        for message in script.requests[request]["messages"]
        if message["role"] == "tool"
    ]


def test_saying_youre_out_of_things_adds_them(api_client: TestClient, assistant_user: TestUser, model) -> None:
    script = model(
        completion(
            calls=[
                call("1", "add_out_of_items", {"items": [{"name": "rice"}, {"name": "paper towels", "store": "aldi"}]})
            ]
        ),
        completion("Added rice and paper towels to the Out of list."),
    )

    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("We're out of rice and paper towels"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] == "Added rice and paper towels to the Out of list."
    assert body["actions"] == [
        {"kind": "restock", "summary": "Added rice to Out of"},
        {"kind": "restock", "summary": "Added paper towels to Out of"},
    ]
    added = tool_results(script)[0]["items"]
    assert [item["status"] for item in added] == ["waiting", "waiting"]

    items = api_client.get(RESTOCK, headers=assistant_user.token).json()["items"]
    assert [(item["name"], item["store"]) for item in items] == [("rice", None), ("paper towels", "aldi")]
    assert {item["addedBy"] for item in items} == {assistant_user.full_name}

    # The system prompt tells the model the date and who it's talking with
    system = script.requests[0]["messages"][0]["content"]
    assert "Wednesday, October 14, 2026" in system
    assert assistant_user.full_name in system
    assert "Out of" in system


def test_reading_changing_and_removing_items(api_client: TestClient, assistant_user: TestUser, model) -> None:
    api_client.post(RESTOCK, headers=assistant_user.token, json={"name": "Milk"})
    api_client.post(RESTOCK, headers=assistant_user.token, json={"name": "Eggs"})
    script = model(completion(calls=[call("1", "get_out_of_list", {})]), completion("Milk and eggs."))
    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("What are we out of?"))
    assert response.status_code == 200, response.text
    assert response.json()["actions"] == []
    listed = {item["name"]: item["id"] for item in tool_results(script)[0]["items"]}
    assert set(listed) == {"Milk", "Eggs"}

    model(
        completion(
            calls=[
                call(
                    "1",
                    "update_out_of_item",
                    {"id": listed["Milk"], "name": "Milk", "quantity": 2, "unit": "count", "note": "oat"},
                ),
                call("2", "remove_out_of_items", {"ids": [listed["Eggs"]]}),
            ]
        ),
        completion("Done."),
    )
    response = api_client.post(
        CHAT,
        headers=assistant_user.token,
        json=user_says("What are we out of?", "Milk and eggs.", "2 oat milks, no eggs"),
    )
    assert response.status_code == 200, response.text
    assert [action["summary"] for action in response.json()["actions"]] == [
        "Updated Milk on Out of",
        "Removed Eggs from Out of",
    ]
    items = api_client.get(RESTOCK, headers=assistant_user.token).json()["items"]
    assert [(item["name"], item["quantity"], item["note"]) for item in items] == [("Milk", 2, "oat")]


def test_marking_bought_and_bad_ids(api_client: TestClient, assistant_user: TestUser, model) -> None:
    item = api_client.post(RESTOCK, headers=assistant_user.token, json={"name": "Coffee"}).json()["items"][0]
    script = model(
        completion(
            calls=[
                call("1", "mark_out_of_items_bought", {"ids": [item["id"]]}),
                call("2", "remove_out_of_items", {"ids": ["coffee"]}),
                call("3", "remove_out_of_items", {"ids": [str(uuid4())]}),
                call("4", "add_out_of_items", {"items": []}),
            ]
        ),
        completion("Marked the coffee bought."),
    )
    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("Got the coffee"))
    assert response.status_code == 200, response.text
    assert [action["summary"] for action in response.json()["actions"]] == ["Marked Coffee bought"]

    bought, not_an_id, missing, empty = tool_results(script)
    assert bought["items"][0]["status"] == "bought"
    assert "isn't an item id" in not_an_id
    assert "isn't on your Out of list" in missing
    assert "arguments don't fit" in empty
    result = api_client.get(RESTOCK, headers=assistant_user.token).json()
    assert result["items"] == []
    assert [entry["name"] for entry in result["recentlyBought"]] == ["Coffee"]


def test_grocery_list_meal_plan_and_recipes(api_client: TestClient, assistant_user: TestUser, model) -> None:
    user = assistant_user
    recipe = user.repos.recipes.create(
        Recipe(user_id=user.user_id, group_id=user.group_id, name=f"Taco night {uuid4().hex[:6]}", description="Tacos")
    )
    api_client.post(RESTOCK, headers=user.token, json={"name": "Tortillas"})
    response = api_client.put(
        "/api/households/groceries/weeks/2026-10-12",
        headers=user.token,
        json={"stores": ["walmart"], "expectedRevision": 0, "skipOnHand": False},
    )
    assert response.status_code == 200, response.text

    script = model(
        completion(
            calls=[
                call("1", "search_recipes", {"query": "taco"}),
                call("2", "plan_meal", {"day": "2026-10-16", "recipe": recipe.slug}),
                call("3", "plan_meal", {"day": "2026-10-17", "title": "Leftovers"}),
                call("4", "get_meal_plan", {"start": "2026-10-12", "end": "2026-10-18"}),
                call("5", "get_grocery_list", {}),
                call("6", "get_recipe", {"recipe": str(recipe.id)}),
                call("7", "plan_meal", {"day": "2026-10-18"}),
            ]
        ),
        completion("Planned tacos for Friday and leftovers for Saturday."),
    )
    response = api_client.post(CHAT, headers=user.token, json=user_says("Plan tacos Friday, leftovers Saturday"))
    assert response.status_code == 200, response.text
    assert [action["summary"] for action in response.json()["actions"]] == [
        f"Planned {recipe.name} for dinner on Fri, Oct 16",
        "Planned Leftovers for dinner on Sat, Oct 17",
    ]

    found, planned, _, plan, grocery_list, details, nothing = tool_results(script)
    assert [entry["slug"] for entry in found["recipes"]] == [recipe.slug]
    assert planned["planned"]["what"] == recipe.name
    assert [(meal["date"], meal["recipe"] or meal["title"]) for meal in plan["meals"]] == [
        ("2026-10-16", recipe.name),
        ("2026-10-17", "Leftovers"),
    ]
    assert grocery_list["week_of"] == "2026-10-12"
    assert grocery_list["items"] == [
        {"name": "Tortillas", "store": "not assigned", "needs": "Tortillas", "bought": False, "from_out_of_list": True}
    ]
    assert details["name"] == recipe.name
    assert "Give a saved recipe or a title" in nothing

    meals = api_client.get(
        "/api/households/mealplans", headers=user.token, params={"start_date": "2026-10-12", "end_date": "2026-10-18"}
    ).json()["items"]
    assert sorted((meal["date"], meal["entryType"]) for meal in meals) == [
        ("2026-10-16", "dinner"),
        ("2026-10-17", "dinner"),
    ]


def test_chat_needs_an_ai_provider(api_client: TestClient, unique_user_fn_scoped: TestUser) -> None:
    response = api_client.post(CHAT, headers=unique_user_fn_scoped.token, json=user_says("We're out of rice"))
    assert response.status_code == 400
    assert "AI provider" in response.json()["detail"]["message"]


def test_provider_failures_are_not_echoed(api_client: TestClient, assistant_user: TestUser, model) -> None:
    model(RuntimeError("upstream said: secret internal page"))
    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("Hi"))
    assert response.status_code == 502
    assert "secret" not in response.text


def test_chat_must_end_with_the_user(api_client: TestClient, assistant_user: TestUser) -> None:
    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("Hi", "Hello!"))
    assert response.status_code == 422


def test_chat_requires_authentication(api_client: TestClient) -> None:
    assert api_client.post(CHAT, json=user_says("Hi")).status_code == 401


def test_tools_only_reach_the_users_household(
    api_client: TestClient, assistant_user: TestUser, h2_user: TestUser, model
) -> None:
    theirs = api_client.post(RESTOCK, headers=h2_user.token, json={"name": "Their bread"}).json()["items"][0]
    script = model(
        completion(calls=[call("1", "get_out_of_list", {}), call("2", "remove_out_of_items", {"ids": [theirs["id"]]})]),
        completion("Nothing to remove."),
    )
    response = api_client.post(CHAT, headers=assistant_user.token, json=user_says("Remove the bread"))
    assert response.status_code == 200, response.text
    listed, removed = tool_results(script)
    assert listed["items"] == []
    assert "isn't on your Out of list" in removed
    assert [item["name"] for item in api_client.get(RESTOCK, headers=h2_user.token).json()["items"]] == ["Their bread"]
