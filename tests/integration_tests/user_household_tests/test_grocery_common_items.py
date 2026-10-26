"""Common items: the ingredients a household has saved products for, which it can add to the list in one tap."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.services.household_services import groceries
from tests.utils import api_routes
from tests.utils.fixture_schemas import TestUser

BASE = "/api/households/groceries"
COMMON = api_routes.households_groceries_common_items
LAST_WEEK = "2026-10-05"
WEEK = "2026-10-12"


@dataclass
class CommonCase:
    client: TestClient
    user: TestUser
    suffix: str = field(default_factory=lambda: uuid4().hex[:8])

    def food(self, name: str, **details: Any) -> dict[str, Any]:
        response = self.client.post(
            "/api/foods", headers=self.user.token, json={"name": f"{name} {self.suffix}", **details}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def product(self, food: dict[str, Any], name: str, store: str, **details: Any) -> dict[str, Any]:
        response = self.client.post(
            f"{BASE}/products",
            headers=self.user.token,
            json={"foodId": food["id"], "name": name, "store": store, **details},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def common(self) -> dict[str, Any]:
        response = self.client.get(COMMON, headers=self.user.token)
        assert response.status_code == 200, response.text
        return response.json()

    def generate(self, stores: list[str], week: str = WEEK) -> dict[str, Any]:
        current = self.client.get(f"{BASE}/weeks/{week}", headers=self.user.token).json()
        payload = {
            "stores": stores,
            "expectedRevision": current["week"]["revision"] if current["week"] else 0,
            "skipOnHand": False,
        }
        response = self.client.put(f"{BASE}/weeks/{week}", headers=self.user.token, json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    def add_to_week(self, view: dict[str, Any], food: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"{BASE}/weeks/{view['weekStart']}/items",
            headers=self.user.token,
            json={"foodId": food["id"], "expectedRevision": view["week"]["revision"]},
        )
        assert response.status_code == 201, response.text
        return response.json()


def item_for(result: dict[str, Any], food: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in result["items"] if item["food"]["id"] == food["id"])


def food_ids(result: dict[str, Any]) -> list[str]:
    return [item["food"]["id"] for item in result["items"]]


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the household's today, which decides the list new items go on"""
    monkeypatch.setattr(groceries, "household_today", lambda: date.fromisoformat("2026-10-14"))


@pytest.fixture
def common_case(api_client: TestClient, unique_user_fn_scoped: TestUser, today: None) -> CommonCase:
    return CommonCase(api_client, unique_user_fn_scoped)


def test_common_items_are_the_ingredients_with_enabled_products(common_case: CommonCase) -> None:
    assert common_case.common() == {"items": [], "nextListWeek": None, "stores": []}

    milk = common_case.food("Milk")
    bananas = common_case.food("Bananas")
    fish_sauce = common_case.food("Fish sauce")
    common_case.food("Saffron")
    backup = common_case.product(milk, "Friendly Farms 2%", "aldi", priority=1)
    first = common_case.product(milk, "Great Value 2%", "walmart")
    common_case.product(bananas, "Bananas", "aldi")
    common_case.product(fish_sauce, "Red Boat", "whole_foods", enabled=False)
    common_case.product(bananas, "Organic bananas", "whole_foods", enabled=False)

    result = common_case.common()
    assert food_ids(result) == [bananas["id"], milk["id"]]
    assert [product["id"] for product in item_for(result, milk)["products"]] == [first["id"], backup["id"]]
    assert [product["name"] for product in item_for(result, bananas)["products"]] == ["Bananas"]
    assert item_for(result, milk)["food"]["name"] == milk["name"]
    assert not any(item["listed"] for item in result["items"])
    assert result["nextListWeek"] is None


def test_aisles_come_from_ingredient_labels(common_case: CommonCase) -> None:
    response = common_case.client.post(
        "/api/groups/labels",
        headers=common_case.user.token,
        json={"name": f"Dairy {common_case.suffix}", "color": "#959595"},
    )
    assert response.status_code == 200, response.text
    label = response.json()
    milk = common_case.food("Milk", labelId=label["id"])
    eggs = common_case.food("Eggs")
    common_case.product(milk, "Great Value 2%", "walmart")
    common_case.product(eggs, "Goldhen, 12 ct", "aldi")

    result = common_case.common()
    assert item_for(result, milk)["aisle"] == label["name"]
    assert item_for(result, eggs)["aisle"] is None


def test_products_start_with_what_the_list_would_buy(common_case: CommonCase) -> None:
    milk = common_case.food("Milk")
    walmart = common_case.product(milk, "Great Value 2%", "walmart")
    aldi = common_case.product(milk, "Friendly Farms 2%", "aldi", priority=1)
    cub = common_case.product(milk, "Cub 2%", "cub", priority=1)
    assert [product["id"] for product in item_for(common_case.common(), milk)["products"]] == [
        walmart["id"],
        cub["id"],
        aldi["id"],
    ]

    # Walmart isn't on this week's trip, and the tie between the others goes to the store chosen first
    view = common_case.generate(["aldi", "cub"])
    view = common_case.add_to_week(view, milk)
    result = common_case.common()
    assert result["stores"] == ["aldi", "cub"]
    products = item_for(result, milk)["products"]
    assert [product["id"] for product in products] == [aldi["id"], cub["id"], walmart["id"]]
    assert view["purchases"][0]["product"]["id"] == products[0]["id"]


def test_listed_means_already_on_the_list_for_another_reason(common_case: CommonCase) -> None:
    milk = common_case.food("Milk")
    bananas = common_case.food("Bananas")
    common_case.product(milk, "Great Value 2%", "walmart")
    common_case.product(bananas, "Bananas", "aldi")

    # Last week's list is behind us, so nothing on it counts
    common_case.add_to_week(common_case.generate(["walmart", "aldi"], week=LAST_WEEK), milk)
    result = common_case.common()
    assert result["nextListWeek"] is None
    assert not item_for(result, milk)["listed"]

    common_case.add_to_week(common_case.generate(["walmart", "aldi"]), milk)
    response = common_case.client.post(
        f"{BASE}/restock",
        headers=common_case.user.token,
        json={"name": bananas["name"], "foodId": bananas["id"]},
    )
    assert response.status_code == 201, response.text
    result = common_case.common()
    assert result["nextListWeek"] == WEEK
    assert item_for(result, milk)["listed"]
    # Bananas are on the list as an Out of item, which the Out of list reports
    assert not item_for(result, bananas)["listed"]

    view = common_case.client.get(f"{BASE}/weeks/{WEEK}", headers=common_case.user.token).json()
    row = next(item for item in view["shoppingList"]["listItems"] if item["foodId"] == milk["id"])
    response = common_case.client.put(
        f"{BASE}/weeks/{WEEK}/checked",
        headers=common_case.user.token,
        json={"itemIds": [row["id"]], "checked": True, "expectedRevision": view["week"]["revision"]},
    )
    assert response.status_code == 200, response.text
    assert not item_for(common_case.common(), milk)["listed"]


def test_common_items_are_household_scoped(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser
) -> None:
    case = CommonCase(api_client, unique_user)
    milk = case.food("Milk")
    case.product(milk, "Great Value 2%", "walmart")
    assert milk["id"] in food_ids(case.common())

    # h2_user shares the group, and so the ingredient, but not the household's products
    for other in [h2_user, g2_user]:
        assert milk["id"] not in food_ids(CommonCase(api_client, other).common())
    assert api_client.get(COMMON).status_code == 401
