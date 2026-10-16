"""The Out of list: things the household has run out of, carried onto the newest grocery list until bought."""

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit, RecipeIngredient
from mealie.services.household_services import groceries
from tests.utils.fixture_schemas import TestUser

BASE = "/api/households/groceries"
RESTOCK = f"{BASE}/restock"
WEEK = "2026-10-12"
NEXT_WEEK = "2026-10-19"


@dataclass
class RestockCase:
    client: TestClient
    user: TestUser
    food: dict[str, Any]

    def get(self) -> dict[str, Any]:
        response = self.client.get(RESTOCK, headers=self.user.token)
        assert response.status_code == 200, response.text
        return response.json()

    def add(self, name: str, **details: Any) -> dict[str, Any]:
        response = self.client.post(RESTOCK, headers=self.user.token, json={"name": name, **details})
        assert response.status_code == 201, response.text
        return response.json()

    def week(self, week: str = WEEK) -> dict[str, Any]:
        response = self.client.get(f"{BASE}/weeks/{week}", headers=self.user.token)
        assert response.status_code == 200, response.text
        return response.json()

    def generate(self, week: str = WEEK) -> dict[str, Any]:
        current = self.week(week)
        payload = {
            "stores": ["walmart", "aldi"],
            "expectedRevision": current["week"]["revision"] if current["week"] else 0,
            "skipOnHand": False,
        }
        response = self.client.put(f"{BASE}/weeks/{week}", headers=self.user.token, json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    def check(self, view: dict[str, Any], item_ids: list[str], checked: bool = True) -> dict[str, Any]:
        response = self.client.put(
            f"{BASE}/weeks/{view['weekStart']}/checked",
            headers=self.user.token,
            json={"itemIds": item_ids, "checked": checked, "expectedRevision": view["week"]["revision"]},
        )
        assert response.status_code == 200, response.text
        return response.json()


def restock_rows(view: dict[str, Any]) -> list[dict[str, Any]]:
    items = view["shoppingList"]["listItems"] if view["shoppingList"] else []
    return [item for item in items if item["extras"].get("shop.source") == "restock"]


def named(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in result["items"] if item["name"] == name)


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch):
    """Pin the household's today, which decides which lists are still ahead"""

    def set_today(value: str) -> None:
        monkeypatch.setattr(groceries, "household_today", lambda: date.fromisoformat(value))

    set_today("2026-10-14")
    return set_today


@pytest.fixture
def restock_case(api_client: TestClient, unique_user_fn_scoped: TestUser, today) -> RestockCase:
    user = unique_user_fn_scoped
    response = api_client.post("/api/foods", headers=user.token, json={"name": f"Jasmine rice {uuid4().hex[:8]}"})
    assert response.status_code == 201, response.text
    return RestockCase(api_client, user, response.json())


def test_items_wait_for_the_next_list_then_join_it(restock_case: RestockCase) -> None:
    result = restock_case.add("Paper towels")
    item = named(result, "Paper towels")
    assert item["status"] == "waiting"
    assert item["shoppingListItemId"] is None
    assert result["nextListWeek"] is None

    view = restock_case.generate()
    rows = restock_rows(view)
    assert [row["note"] for row in rows] == ["Paper towels"]
    assert rows[0]["quantity"] == 0
    assert rows[0]["display"] == "Paper towels"
    assert view["purchases"][0]["foodName"] == "Paper towels"

    item = named(restock_case.get(), "Paper towels")
    assert item["status"] == "listed"
    assert item["weekStart"] == WEEK
    assert item["shoppingListItemId"] == rows[0]["id"]


def test_items_go_straight_onto_an_existing_list(restock_case: RestockCase) -> None:
    before = restock_case.generate()
    result = restock_case.add("Dish soap", note="the lemon one", store="aldi")
    assert result["nextListWeek"] == WEEK
    assert named(result, "Dish soap")["status"] == "listed"

    view = restock_case.week()
    rows = restock_rows(view)
    assert [row["note"] for row in rows] == ["Dish soap (the lemon one)"]
    assert rows[0]["extras"]["shop.store_override"] == "aldi"
    assert view["week"]["revision"] > before["week"]["revision"]
    assert view["purchases"][0]["store"] == "aldi"


def test_saying_it_again_updates_instead_of_duplicating(restock_case: RestockCase) -> None:
    restock_case.generate()
    restock_case.add("Rice")
    result = restock_case.add("  rice ", quantity=2, unit="pound")
    assert [item["name"] for item in result["items"]] == ["Rice"]
    assert named(result, "Rice")["quantity"] == 2
    assert named(result, "Rice")["unit"] == "pound"

    rows = restock_rows(restock_case.week())
    assert len(rows) == 1
    assert rows[0]["quantity"] == 2


def test_food_names_link_and_combine_with_recipe_demand(restock_case: RestockCase) -> None:
    client, user, food = restock_case.client, restock_case.user, restock_case.food
    response = client.post(
        "/api/units", headers=user.token, json={"name": "lb", "standardUnit": "pound", "standardQuantity": 1}
    )
    assert response.status_code == 201, response.text
    unit = response.json()
    response = client.post(
        f"{BASE}/products",
        headers=user.token,
        json={
            "foodId": food["id"],
            "name": "Big bag of rice",
            "store": "walmart",
            "packageQuantity": 2,
            "packageUnit": "pound",
        },
    )
    assert response.status_code == 201, response.text

    # With nothing else asking for it, "the usual amount" is one package
    result = restock_case.add(food["name"].upper())
    assert named(result, food["name"].upper())["foodId"] == food["id"]
    view = restock_case.generate()
    assert len(view["purchases"]) == 1
    assert view["purchases"][0]["packageCount"] == 1
    assert view["purchases"][0]["quantityNote"] == ""

    # A recipe that needs 3 lb rounds up past the one package, on the same card
    recipe = user.repos.recipes.create(
        Recipe(
            user_id=user.user_id,
            group_id=user.group_id,
            name=f"Rice night {uuid4().hex[:8]}",
            recipe_ingredient=[
                RecipeIngredient(
                    quantity=3, food=IngredientFood.model_validate(food), unit=IngredientUnit.model_validate(unit)
                )
            ],
        )
    )
    response = client.post(
        "/api/households/mealplans",
        headers=user.token,
        json={"date": WEEK, "entryType": "dinner", "recipeId": str(recipe.id)},
    )
    assert response.status_code == 201, response.text
    view = restock_case.generate()
    assert len(view["purchases"]) == 1
    purchase = view["purchases"][0]
    assert len(purchase["items"]) == 2
    assert purchase["product"]["name"] == "Big bag of rice"
    assert purchase["packageCount"] == 2


def test_checking_the_row_off_marks_it_bought(restock_case: RestockCase) -> None:
    view = restock_case.generate()
    restock_case.add("Coffee filters")
    view = restock_case.week()
    row = restock_rows(view)[0]

    view = restock_case.check(view, [row["id"]])
    result = restock_case.get()
    assert result["items"] == []
    assert [item["name"] for item in result["recentlyBought"]] == ["Coffee filters"]
    assert result["recentlyBought"][0]["status"] == "bought"
    assert result["recentlyBought"][0]["boughtAt"]

    restock_case.check(view, [row["id"]], checked=False)
    result = restock_case.get()
    assert named(result, "Coffee filters")["status"] == "listed"
    assert result["recentlyBought"] == []


def test_marking_bought_on_the_out_of_list_checks_the_row(restock_case: RestockCase) -> None:
    restock_case.generate()
    item = named(restock_case.add("Foil"), "Foil")

    response = restock_case.client.put(
        f"{RESTOCK}/{item['id']}/bought", headers=restock_case.user.token, json={"bought": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["recentlyBought"][0]["id"] == item["id"]
    assert restock_rows(restock_case.week())[0]["checked"] is True

    response = restock_case.client.put(
        f"{RESTOCK}/{item['id']}/bought", headers=restock_case.user.token, json={"bought": False}
    )
    assert response.status_code == 200, response.text
    assert named(response.json(), "Foil")["status"] == "listed"
    assert restock_rows(restock_case.week())[0]["checked"] is False


def test_bought_while_waiting_needs_no_list(restock_case: RestockCase) -> None:
    item = named(restock_case.add("Batteries"), "Batteries")
    response = restock_case.client.put(
        f"{RESTOCK}/{item['id']}/bought", headers=restock_case.user.token, json={"bought": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert restock_rows(restock_case.generate()) == []


def test_unbought_items_move_to_a_newer_list(restock_case: RestockCase) -> None:
    restock_case.generate()
    restock_case.add("Milk")
    restock_case.add("Eggs")
    view = restock_case.week()
    eggs = next(row for row in restock_rows(view) if row["note"] == "Eggs")
    restock_case.check(view, [eggs["id"]])

    newer = restock_case.generate(NEXT_WEEK)
    assert [row["note"] for row in restock_rows(newer)] == ["Milk"]
    older = restock_case.week()
    # Bought stays where it was bought
    assert [row["note"] for row in restock_rows(older)] == ["Eggs"]
    assert named(restock_case.get(), "Milk")["weekStart"] == NEXT_WEEK

    # New items go on the newest list too
    restock_case.add("Butter")
    assert sorted(row["note"] for row in restock_rows(restock_case.week(NEXT_WEEK))) == ["Butter", "Milk"]


def test_lists_for_weeks_that_ended_are_not_used(restock_case: RestockCase, today) -> None:
    restock_case.generate()
    restock_case.add("Bread")
    today("2026-10-21")

    result = restock_case.add("Bananas")
    assert result["nextListWeek"] is None
    assert named(result, "Bananas")["status"] == "waiting"
    # Still on last week's list, but that trip is over, so it waits for the next one
    assert named(result, "Bread")["status"] == "waiting"
    assert [row["note"] for row in restock_rows(restock_case.week())] == ["Bread"]

    view = restock_case.generate(NEXT_WEEK)
    assert sorted(row["note"] for row in restock_rows(view)) == ["Bananas", "Bread"]
    assert restock_rows(restock_case.week()) == []


def test_deleting_the_row_from_the_list_removes_the_item(restock_case: RestockCase) -> None:
    restock_case.generate()
    restock_case.add("Sponges")
    view = restock_case.week()
    row = restock_rows(view)[0]
    response = restock_case.client.post(
        f"{BASE}/weeks/{WEEK}/items/delete",
        headers=restock_case.user.token,
        json={"itemIds": [row["id"]], "expectedRevision": view["week"]["revision"]},
    )
    assert response.status_code == 200, response.text
    assert restock_case.get()["items"] == []


def test_removing_the_item_removes_its_row(restock_case: RestockCase) -> None:
    restock_case.generate()
    item = named(restock_case.add("Trash bags"), "Trash bags")
    response = restock_case.client.delete(f"{RESTOCK}/{item['id']}", headers=restock_case.user.token)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert restock_rows(restock_case.week()) == []


def test_editing_carries_over_to_the_row(restock_case: RestockCase) -> None:
    restock_case.generate()
    item = named(restock_case.add("Olive oil"), "Olive oil")
    response = restock_case.client.put(
        f"{RESTOCK}/{item['id']}",
        headers=restock_case.user.token,
        json={"name": "Olive oil", "quantity": 2, "unit": "count", "store": "aldi", "note": "big bottles"},
    )
    assert response.status_code == 200, response.text
    edited = named(response.json(), "Olive oil")
    assert edited["store"] == "aldi"
    assert edited["note"] == "big bottles"

    row = restock_rows(restock_case.week())[0]
    assert row["quantity"] == 2
    assert row["note"] == "Olive oil (big bottles)"
    assert row["extras"]["shop.store_override"] == "aldi"


def test_a_unit_needs_an_amount(restock_case: RestockCase) -> None:
    response = restock_case.client.post(
        RESTOCK, headers=restock_case.user.token, json={"name": "Flour", "unit": "pound"}
    )
    assert response.status_code == 422


def test_out_of_list_requires_authentication(api_client: TestClient) -> None:
    assert api_client.get(RESTOCK).status_code == 401
    assert api_client.post(RESTOCK, json={"name": "Rice"}).status_code == 401


def test_out_of_list_is_household_scoped(restock_case: RestockCase, h2_user: TestUser, g2_user: TestUser) -> None:
    restock_case.generate()
    item = named(restock_case.add("Cereal"), "Cereal")
    for other in [h2_user, g2_user]:
        result = restock_case.client.get(RESTOCK, headers=other.token).json()
        assert item["id"] not in [entry["id"] for entry in result["items"]]
        assert restock_case.client.delete(f"{RESTOCK}/{item['id']}", headers=other.token).status_code == 404
        response = restock_case.client.put(f"{RESTOCK}/{item['id']}/bought", headers=other.token, json={})
        assert response.status_code == 404
        # Their own Out of list never lands on this household's grocery list
        response = restock_case.client.post(RESTOCK, headers=other.token, json={"name": "Cereal"})
        assert response.status_code == 201
    assert [row["note"] for row in restock_rows(restock_case.week())] == ["Cereal"]
    assert [entry["name"] for entry in restock_case.get()["items"]] == ["Cereal"]


def test_deleting_the_food_keeps_the_item(restock_case: RestockCase) -> None:
    name = restock_case.food["name"]
    assert named(restock_case.add(name), name)["foodId"] == restock_case.food["id"]
    response = restock_case.client.delete(f"/api/foods/{restock_case.food['id']}", headers=restock_case.user.token)
    assert response.status_code == 200, response.text
    item = named(restock_case.get(), name)
    assert item["foodId"] is None
    assert item["food"] is None


def test_merged_foods_keep_their_items(restock_case: RestockCase) -> None:
    name = restock_case.food["name"]
    restock_case.add(name)
    response = restock_case.client.post("/api/foods", headers=restock_case.user.token, json={"name": f"Rice {uuid4()}"})
    assert response.status_code == 201, response.text
    target = response.json()
    response = restock_case.client.put(
        "/api/foods/merge",
        headers=restock_case.user.token,
        json={"fromFood": restock_case.food["id"], "toFood": target["id"]},
    )
    assert response.status_code == 200, response.text
    assert named(restock_case.get(), name)["foodId"] == target["id"]
