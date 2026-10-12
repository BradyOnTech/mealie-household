from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit, RecipeIngredient
from tests import utils
from tests.utils.fixture_schemas import TestUser

BASE = "/api/households/groceries"
WEEK = "2026-10-12"


@dataclass
class GroceryCase:
    client: TestClient
    user: TestUser
    food: dict[str, Any]
    product: dict[str, Any]
    meals: list[dict[str, Any]]

    def generate(self, **changes: Any) -> dict[str, Any]:
        current = self.client.get(f"{BASE}/weeks/{WEEK}", headers=self.user.token).json()
        payload = {
            "stores": ["walmart", "aldi"],
            "expectedRevision": current["week"]["revision"] if current["week"] else 0,
            "skipOnHand": False,
            **changes,
        }
        response = self.client.put(f"{BASE}/weeks/{WEEK}", headers=self.user.token, json=payload)
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def grocery_case(api_client: TestClient, unique_user_fn_scoped: TestUser) -> GroceryCase:
    user = unique_user_fn_scoped
    response = api_client.post("/api/foods", headers=user.token, json={"name": f"Ground turkey {uuid4().hex[:8]}"})
    assert response.status_code == 201, response.text
    food = response.json()
    response = api_client.post(
        "/api/units",
        headers=user.token,
        json={
            "name": "lb",
            "standardUnit": "pound",
            "standardQuantity": 1,
        },
    )
    assert response.status_code == 201, response.text
    unit = response.json()
    meals = []
    for i, quantity in enumerate([0.6, 1.0]):
        recipe = user.repos.recipes.create(
            Recipe(
                user_id=user.user_id,
                group_id=user.group_id,
                name=f"Turkey dinner {uuid4().hex[:8]}",
                recipe_ingredient=[
                    RecipeIngredient(
                        quantity=quantity,
                        food=IngredientFood.model_validate(food),
                        unit=IngredientUnit.model_validate(unit),
                    )
                ],
            )
        )
        response = api_client.post(
            "/api/households/mealplans",
            headers=user.token,
            json={
                "date": f"2026-10-{12 + i}",
                "entryType": "dinner",
                "recipeId": str(recipe.id),
            },
        )
        assert response.status_code == 201, response.text
        meals.append(response.json())
    response = api_client.post(
        f"{BASE}/products",
        headers=user.token,
        json={
            "foodId": food["id"],
            "name": "Our usual 1 lb turkey",
            "store": "walmart",
            "url": "https://www.walmart.com/ip/household-test/123456",
            "packageQuantity": 1,
            "packageUnit": "pound",
        },
    )
    assert response.status_code == 201, response.text
    return GroceryCase(api_client, user, food, response.json(), meals)


def pending(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in view["shoppingList"]["listItems"] if not item["checked"]]


def test_week_generation_aggregates_then_rounds_and_is_repeat_safe(grocery_case: GroceryCase) -> None:
    first = grocery_case.generate()
    second = grocery_case.generate()
    assert first["week"]["shoppingListId"] == second["week"]["shoppingListId"]
    assert len(pending(second)) == 1
    assert pending(second)[0]["id"] == pending(first)[0]["id"]
    assert pending(second)[0]["quantity"] == pytest.approx(1.6)
    assert second["purchases"][0]["packageCount"] == 2
    assert second["purchases"][0]["store"] == "walmart"


def test_active_store_uses_backup_product(grocery_case: GroceryCase) -> None:
    response = grocery_case.client.post(
        f"{BASE}/products",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "name": "Aldi backup turkey",
            "store": "aldi",
            "priority": 10,
        },
    )
    assert response.status_code == 201
    view = grocery_case.generate(stores=["aldi"])
    assert view["purchases"][0]["product"]["name"] == "Aldi backup turkey"


def test_manual_override_survives_regeneration(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    item_id = pending(view)[0]["id"]
    response = grocery_case.client.put(
        f"{BASE}/weeks/{WEEK}/assignment",
        headers=grocery_case.user.token,
        json={
            "itemIds": [item_id],
            "store": "aldi",
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == 200, response.text
    updated = grocery_case.generate()
    assert pending(updated)[0]["id"] == item_id
    assert pending(updated)[0]["extras"]["shop.store_override"] == "aldi"
    assert updated["purchases"][0]["store"] == "aldi"
    assert updated["purchases"][0]["product"] is None


def test_purchased_quantities_are_kept_and_only_additional_demand_is_added(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    response = grocery_case.client.put(
        f"{BASE}/weeks/{WEEK}/checked",
        headers=grocery_case.user.token,
        json={
            "itemIds": [pending(view)[0]["id"]],
            "checked": True,
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == 200, response.text
    unchanged = grocery_case.generate()
    assert not pending(unchanged)
    increased = grocery_case.generate(mealScales={str(grocery_case.meals[0]["id"]): 2})
    assert len(pending(increased)) == 1
    # Two 1 lb packages were purchased, leaving 0.4 lb of package overage available.
    assert pending(increased)[0]["quantity"] == pytest.approx(0.2)
    bought = [item for item in increased["shoppingList"]["listItems"] if item["checked"]]
    assert bought[0]["quantity"] == pytest.approx(1.6)
    assert increased["purchases"][0]["packageCount"] == 1


def test_pantry_updates_after_purchase_do_not_count_the_purchase_twice(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    response = grocery_case.client.put(
        f"{BASE}/weeks/{WEEK}/checked",
        headers=grocery_case.user.token,
        json={
            "itemIds": [pending(view)[0]["id"]],
            "checked": True,
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == 200
    response = grocery_case.client.post(
        f"{BASE}/rules",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "kind": "pantry",
            "quantity": 2,
            "unit": "pound",
        },
    )
    assert response.status_code == 201
    increased = grocery_case.generate(mealScales={str(grocery_case.meals[0]["id"]): 3})
    assert pending(increased)[0]["quantity"] == pytest.approx(0.8)
    assert any("starting stock" in warning for warning in increased["warnings"])


def test_pantry_deducts_once_and_full_coverage_removes_demand(grocery_case: GroceryCase) -> None:
    response = grocery_case.client.post(
        f"{BASE}/rules",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "kind": "pantry",
            "quantity": 0.4,
            "unit": "pound",
        },
    )
    assert response.status_code == 201
    rule = response.json()
    view = grocery_case.generate()
    assert pending(view)[0]["quantity"] == pytest.approx(1.2)
    response = grocery_case.client.put(
        f"{BASE}/rules/{rule['id']}",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "kind": "pantry",
            "quantity": 2,
            "unit": "pound",
        },
    )
    assert response.status_code == 200
    assert not pending(grocery_case.generate())


@pytest.mark.parametrize("mode,total", [("minimum", 2), ("extra", 3.6)])
def test_recurring_targets_and_extra_amounts(grocery_case: GroceryCase, mode: str, total: float) -> None:
    response = grocery_case.client.post(
        f"{BASE}/rules",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "kind": "recurring",
            "quantity": 2,
            "unit": "pound",
            "mode": mode,
        },
    )
    assert response.status_code == 201
    view = grocery_case.generate()
    assert sum(item["quantity"] for item in pending(view)) == pytest.approx(total)
    assert view["purchases"][0]["packageCount"] == (2 if mode == "minimum" else 4)


def test_manual_items_survive_and_packages_round_after_manual_aggregation(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    response = grocery_case.client.post(
        f"{BASE}/weeks/{WEEK}/items",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "quantity": 0.3,
            "unit": "pound",
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == 201, response.text
    updated = grocery_case.generate()
    assert len(pending(updated)) == 2
    assert any(item["extras"].get("shop.source") == "manual" for item in pending(updated))
    assert len(updated["purchases"]) == 1
    assert updated["purchases"][0]["packageCount"] == 2


def test_unknown_units_do_not_become_package_counts(grocery_case: GroceryCase) -> None:
    payload = {
        key: value
        for key, value in grocery_case.product.items()
        if key not in {"id", "food", "groupId", "householdId", "createdAt", "updatedAt"}
    }
    payload["packageUnit"] = "cup"
    response = grocery_case.client.put(
        f"{BASE}/products/{grocery_case.product['id']}", headers=grocery_case.user.token, json=payload
    )
    assert response.status_code == 200
    purchase = grocery_case.generate()["purchases"][0]
    assert purchase["packageCount"] is None
    assert "incompatible" in purchase["quantityNote"]


def test_changed_plan_removes_only_generated_items(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    response = grocery_case.client.post(
        f"{BASE}/weeks/{WEEK}/items",
        headers=grocery_case.user.token,
        json={
            "note": "Paper towels",
            "quantity": 1,
            "unit": "count",
            "store": "cub",
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == 201
    for meal in grocery_case.meals:
        response = grocery_case.client.delete(
            f"/api/households/mealplans/{meal['id']}", headers=grocery_case.user.token
        )
        assert response.status_code == 200
    updated = grocery_case.generate()
    assert len(pending(updated)) == 1
    assert pending(updated)[0]["note"] == "Paper towels"


def test_stale_revision_fails_without_changing_list(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate()
    response = grocery_case.client.put(
        f"{BASE}/weeks/{WEEK}",
        headers=grocery_case.user.token,
        json={
            "stores": ["aldi"],
            "expectedRevision": 0,
        },
    )
    assert response.status_code == 409
    current = grocery_case.client.get(f"{BASE}/weeks/{WEEK}", headers=grocery_case.user.token).json()
    assert current["week"]["revision"] == view["week"]["revision"]
    assert current["week"]["stores"] == ["walmart", "aldi"]


def test_foreign_meal_multiplier_rolls_back_new_week(grocery_case: GroceryCase) -> None:
    response = grocery_case.client.put(
        f"{BASE}/weeks/{WEEK}",
        headers=grocery_case.user.token,
        json={
            "stores": ["walmart"],
            "mealScales": {"999999": 2},
            "expectedRevision": 0,
        },
    )
    assert response.status_code == 400
    assert grocery_case.client.get(f"{BASE}/weeks/{WEEK}", headers=grocery_case.user.token).json()["week"] is None


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://www.walmart.com/ip/1", "https://user:password@www.walmart.com/ip/1"]
)
def test_invalid_product_links_are_rejected(grocery_case: GroceryCase, url: str) -> None:
    response = grocery_case.client.post(
        f"{BASE}/products",
        headers=grocery_case.user.token,
        json={
            "foodId": grocery_case.food["id"],
            "name": "A product",
            "store": "walmart",
            "url": url,
        },
    )
    assert response.status_code == 422


def test_groceries_requires_authentication(api_client: TestClient) -> None:
    for path in ["products", "rules", f"weeks/{WEEK}", f"suggestions?plan_date={WEEK}"]:
        assert api_client.get(f"{BASE}/{path}").status_code == 401


def test_product_and_list_data_are_household_scoped(
    grocery_case: GroceryCase, h2_user: TestUser, g2_user: TestUser
) -> None:
    view = grocery_case.generate()
    for other in [h2_user, g2_user]:
        products = grocery_case.client.get(f"{BASE}/products", headers=other.token).json()
        assert grocery_case.product["id"] not in [product["id"] for product in products]
        assert (
            grocery_case.client.delete(f"{BASE}/products/{grocery_case.product['id']}", headers=other.token).status_code
            == 404
        )
        response = grocery_case.client.put(
            f"{BASE}/weeks/{WEEK}/checked",
            headers=other.token,
            json={
                "itemIds": [pending(view)[0]["id"]],
                "checked": True,
                "expectedRevision": 0,
            },
        )
        assert response.status_code == 404
        response = grocery_case.client.post(
            f"{BASE}/products",
            headers=other.token,
            json={
                "foodId": grocery_case.food["id"],
                "name": "Foreign ingredient",
                "store": "walmart",
            },
        )
        assert response.status_code == 404


def test_recipe_multiplier_zero_is_leftovers(grocery_case: GroceryCase) -> None:
    view = grocery_case.generate(mealScales={str(grocery_case.meals[0]["id"]): 0})
    assert pending(view)[0]["quantity"] == pytest.approx(1.0)


@pytest.mark.parametrize("separate_household", [False, True])
def test_members_share_only_their_own_household_groceries(
    grocery_case: GroceryCase, admin_token: dict[str, str], separate_household: bool
) -> None:
    client = grocery_case.client
    group = client.get("/api/groups/self", headers=grocery_case.user.token).json()
    household = client.get("/api/households/self", headers=grocery_case.user.token).json()
    household_name = household["name"]
    if separate_household:
        household_name = f"Other household {uuid4().hex[:8]}"
        response = client.post(
            "/api/admin/households", headers=admin_token, json={"name": household_name, "groupId": group["id"]}
        )
        assert response.status_code == 201, response.text
    email = f"groceries-{uuid4().hex}@example.test"
    response = client.post(
        "/api/admin/users",
        headers=admin_token,
        json={
            "username": f"groceries-{uuid4().hex}",
            "email": email,
            "fullName": "Grocery test member",
            "password": "local-test-only-password",
            "group": group["name"],
            "household": household_name,
            "admin": False,
        },
    )
    assert response.status_code == 201, response.text
    token = utils.login({"username": email, "password": "local-test-only-password"}, client)
    member = client.get("/api/users/self", headers=token).json()
    assert member["groupId"] == group["id"]
    assert (member["householdId"] != household["id"]) == separate_household

    view = grocery_case.generate()
    products = client.get(f"{BASE}/products", headers=token).json()
    week = client.get(f"{BASE}/weeks/{WEEK}", headers=token).json()
    if separate_household:
        assert grocery_case.product["id"] not in [product["id"] for product in products]
        assert week["week"] is None
        assert client.delete(f"{BASE}/products/{grocery_case.product['id']}", headers=token).status_code == 404
        # Foods are group-scoped, but each household can save its own product preference.
        response = client.post(
            f"{BASE}/products",
            headers=token,
            json={"foodId": grocery_case.food["id"], "name": "Our separate preference", "store": "aldi"},
        )
        assert response.status_code == 201, response.text
        original_products = client.get(f"{BASE}/products", headers=grocery_case.user.token).json()
        assert response.json()["id"] not in [product["id"] for product in original_products]
    else:
        assert grocery_case.product["id"] in [product["id"] for product in products]
        assert week["week"]["shoppingListId"] == view["week"]["shoppingListId"]
    response = client.put(
        f"{BASE}/weeks/{WEEK}/checked",
        headers=token,
        json={
            "itemIds": [pending(view)[0]["id"]],
            "checked": True,
            "expectedRevision": view["week"]["revision"],
        },
    )
    assert response.status_code == (404 if separate_household else 200), response.text
    original = client.get(f"{BASE}/weeks/{WEEK}", headers=grocery_case.user.token).json()
    assert bool(pending(original)) == separate_household


def test_suggestions_exclude_already_planned_recipes(grocery_case: GroceryCase) -> None:
    response = grocery_case.client.get(f"{BASE}/suggestions?plan_date={WEEK}", headers=grocery_case.user.token)
    assert response.status_code == 200, response.text
    planned = {meal["recipeId"] for meal in grocery_case.meals}
    assert not any(suggestion["recipe"]["id"] in planned for suggestion in response.json())


@pytest.mark.parametrize("on_hand", [False, True])
def test_suggestions_score_an_unplanned_recipe_from_its_ingredients(grocery_case: GroceryCase, on_hand: bool) -> None:
    if on_hand:
        household = grocery_case.client.get("/api/households/self", headers=grocery_case.user.token).json()
        food = {**grocery_case.food, "householdsWithIngredientFood": [household["slug"]]}
        response = grocery_case.client.put(f"/api/foods/{food['id']}", headers=grocery_case.user.token, json=food)
        assert response.status_code == 200, response.text
    recipe = grocery_case.user.repos.recipes.create(
        Recipe(
            user_id=grocery_case.user.user_id,
            group_id=grocery_case.user.group_id,
            name=f"Unplanned dinner {uuid4().hex[:8]}",
            rating=5,
            recipe_ingredient=[RecipeIngredient(quantity=1, food=IngredientFood.model_validate(grocery_case.food))],
        )
    )
    response = grocery_case.client.get(f"{BASE}/suggestions?plan_date={WEEK}", headers=grocery_case.user.token)
    assert response.status_code == 200, response.text
    suggestion = next(item for item in response.json() if item["recipe"]["id"] == str(recipe.id))
    assert suggestion["score"] == pytest.approx(75 if on_hand else 60)
    assert "Highly rated" in suggestion["reasons"]
    assert ("Uses 1 ingredient on hand" in suggestion["reasons"]) == on_hand
