"""Pasting a product's store link fills in a new preferred product: its name, store, package size and ingredient."""

import pytest
from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.grocery_product import OpenAIGroceryProduct
from mealie.services.openai import OpenAIService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

MILK_URL = "https://www.walmart.com/ip/Great-Value-Whole-Vitamin-D-Milk-Gallon-128-fl-oz/10450114"


def lookup(api_client: TestClient, user: TestUser, url: str):
    return api_client.post(api_routes.households_groceries_products_lookup, json={"url": url}, headers=user.token)


def add_food(api_client: TestClient, user: TestUser, name: str) -> dict:
    response = api_client.post(api_routes.foods, json={"name": name}, headers=user.token)
    assert response.status_code == 201
    return response.json()


def enable_ai(user: TestUser) -> None:
    provider = user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="test-model", api_key="test-key")
    )
    user.repos.group_ai_provider_settings.update(
        user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=provider.id, audio_provider_id=None, image_provider_id=None),
    )


def stub_ai(monkeypatch: pytest.MonkeyPatch, answer: OpenAIGroceryProduct | Exception) -> list[str]:
    """The AI, answering every question with `answer`; returns the messages it was sent"""

    messages: list[str] = []

    async def get_response(self, prompt, message, *args, **kwargs):
        messages.append(message)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(OpenAIService, "get_response", get_response)
    return messages


def test_the_link_alone_fills_in_the_product(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    milk = add_food(api_client, user, "milk")

    response = lookup(api_client, user, MILK_URL)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Great Value Whole Vitamin D Milk Gallon 128 fl oz"
    assert data["store"] == "walmart"
    assert (data["packageQuantity"], data["packageUnit"]) == (128, "fluid_ounce")
    assert data["food"]["id"] == milk["id"]
    assert data["newFoodName"] is None
    assert data["readWithAi"] is False


def test_ai_tidies_the_name_and_picks_the_ingredient(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    user = unique_user_fn_scoped
    enable_ai(user)
    milk = add_food(api_client, user, "milk")
    messages = stub_ai(
        monkeypatch,
        OpenAIGroceryProduct(name="Great Value Whole Vitamin D Milk, 1 gal", ingredient="Milk", package_quantity=1),
    )

    data = lookup(api_client, user, MILK_URL).json()

    assert "Great Value Whole Vitamin D Milk Gallon 128 fl oz" in messages[0]
    assert data["readWithAi"] is True
    assert data["name"] == "Great Value Whole Vitamin D Milk, 1 gal"
    assert data["food"]["id"] == milk["id"]
    # the link's own size stands; the AI's unitless answer couldn't replace it anyway
    assert (data["packageQuantity"], data["packageUnit"]) == (128, "fluid_ounce")


def test_ai_names_an_ingredient_the_household_doesnt_have(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    """Name matching alone would call oat milk "milk"; the AI knows better, and suggests adding oat milk."""

    user = unique_user_fn_scoped
    enable_ai(user)
    add_food(api_client, user, "milk")
    stub_ai(monkeypatch, OpenAIGroceryProduct(name="Oatly Oat Milk, 64 fl oz", ingredient="oat milk"))

    data = lookup(api_client, user, "https://www.walmart.com/ip/Oatly-Oat-Milk-64-fl-oz/123456789").json()

    assert data["food"] is None
    assert data["newFoodName"] == "oat milk"
    assert (data["packageQuantity"], data["packageUnit"]) == (64, "fluid_ounce")


def test_ai_fills_a_size_the_link_doesnt_give(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    user = unique_user_fn_scoped
    enable_ai(user)
    stub_ai(
        monkeypatch,
        OpenAIGroceryProduct(
            name="Kemps Select Whole Milk, 1 gal", ingredient="milk", package_quantity=128, package_unit="fluid_ounce"
        ),
    )

    data = lookup(api_client, user, "https://cub.com/product/kemps-select-whole-milk-id-00041483022011").json()

    assert data["store"] == "cub"
    assert (data["packageQuantity"], data["packageUnit"]) == (128, "fluid_ounce")


def test_an_ai_problem_still_leaves_what_the_link_says(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    user = unique_user_fn_scoped
    enable_ai(user)
    milk = add_food(api_client, user, "milk")
    stub_ai(monkeypatch, RuntimeError("provider unavailable"))

    response = lookup(api_client, user, MILK_URL)

    assert response.status_code == 200
    data = response.json()
    assert data["readWithAi"] is False
    assert data["name"] == "Great Value Whole Vitamin D Milk Gallon 128 fl oz"
    assert data["food"]["id"] == milk["id"]


@pytest.mark.parametrize("url", ["http://www.walmart.com/ip/Milk/1", "not a link", ""])
def test_only_https_links_are_read(api_client: TestClient, unique_user: TestUser, url: str):
    assert lookup(api_client, unique_user, url).status_code == 422
