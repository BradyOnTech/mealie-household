from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from math import ceil, isfinite
from uuid import UUID

from dateutil.tz import tzlocal
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from mealie.db.models._model_utils.datetime import get_utc_now
from mealie.db.models.household.grocery import GroceryRestockItem, GroceryWeek
from mealie.db.models.household.shopping_list import ShoppingListItem
from mealie.repos.all_repositories import AllRepositories, get_repositories
from mealie.schema.grocery.grocery import (
    GroceryCommonItemList,
    GroceryCommonItemOut,
    GroceryFoodRuleCreate,
    GroceryFoodRuleOut,
    GroceryFoodRuleSave,
    GroceryItemAssignment,
    GroceryItemCheck,
    GroceryItemDelete,
    GroceryManualItemCreate,
    GroceryProductCreate,
    GroceryProductOut,
    GroceryProductSave,
    GroceryPurchaseOut,
    GroceryRestockCreate,
    GroceryRestockList,
    GroceryRestockOut,
    GroceryRestockStatus,
    GroceryRuleKind,
    GroceryStore,
    GrocerySuggestionOut,
    GroceryUnit,
    GroceryWeekGenerate,
    GroceryWeekView,
)
from mealie.schema.household.group_shopping_list import (
    ShoppingListItemBase,
    ShoppingListItemCreate,
    ShoppingListItemOut,
    ShoppingListItemUpdateBulk,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.schema.meal_plan.plan_rules import PlanRulesDay, PlanRulesType
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientUnit
from mealie.schema.response.pagination import OrderDirection, PaginationQuery
from mealie.services._base_service import BaseService
from mealie.services.household_services.shopping_lists import ShoppingListService
from mealie.services.parser_services.parser_utils import UnitConverter
from mealie.services.query_filter.builder import QueryFilterBuilder

SOURCE = "shop.source"
STORE_OVERRIDE = "shop.store_override"
PRODUCT_OVERRIDE = "shop.product_override"
PURCHASED_AMOUNT = "shop.purchased_amount"
PURCHASED_UNIT = "shop.purchased_unit"
RESTOCK_ID = "shop.restock_id"
EPSILON = 1e-8
RESTOCK_RECENT = timedelta(days=14)
"""How long a bought item stays under "recently bought" on the Out of list"""
RESTOCK_KEEP = timedelta(days=90)
"""How long bought items are kept at all"""


def monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def household_today() -> date:
    """Today by the server's clock, which the Docker setup puts in the household's time zone"""
    return datetime.now(tz=tzlocal()).date()


def is_usual_amount(item: ShoppingListItemBase) -> bool:
    """An Out of item with no amount given, meaning one of whatever the household normally buys"""
    return (item.extras or {}).get(SOURCE) == "restock" and not item.quantity


def choose_product(
    products: list[GroceryProductOut],
    food_id: UUID | None,
    stores: Sequence[str],
    store_override: str | None = None,
    product_override: str | None = None,
) -> GroceryProductOut | None:
    candidates = [product for product in products if product.enabled and product.food_id == food_id]
    if product_override:
        return next((product for product in candidates if str(product.id) == product_override), None)
    if store_override:
        candidates = [product for product in candidates if product.store == store_override]
    else:
        candidates = [product for product in candidates if product.store in stores]
    order = {store: i for i, store in enumerate(stores)}
    return (
        min(
            candidates,
            key=lambda product: (product.priority, order.get(product.store, 99), product.name, str(product.id)),
        )
        if candidates
        else None
    )


def convert_amount(quantity: float, source: str, target: str) -> float | None:
    """Package and inventory math is strict: no density guesses or ounce/fluid-ounce reinterpretation."""
    if source == target:
        return quantity
    if "count" in (source, target):
        return None
    converter = UnitConverter()
    source_unit = converter.parse(source, strict=True)
    target_unit = converter.parse(target, strict=True)
    if not source_unit.is_compatible_with(target_unit):
        return None
    return float((quantity * source_unit).to(target_unit).magnitude)


def item_standard_amount(item: ShoppingListItemBase, units: dict[UUID, IngredientUnit]) -> tuple[float, str] | None:
    if not item.quantity or item.quantity < 0:
        return None
    unit = item.unit or (units.get(item.unit_id) if item.unit_id else None)
    if unit is None:
        return item.quantity, "count"
    if not unit.standard_unit or not unit.standard_quantity:
        return None
    return item.quantity * unit.standard_quantity, unit.standard_unit


def amount_in_item_unit(
    amount: float, standard: str, item: ShoppingListItemBase, units: dict[UUID, IngredientUnit]
) -> float | None:
    unit = item.unit or (units.get(item.unit_id) if item.unit_id else None)
    if unit is None:
        return amount if standard == "count" else None
    if not unit.standard_unit or not unit.standard_quantity:
        return None
    converted = convert_amount(amount, standard, unit.standard_unit)
    return None if converted is None else converted / unit.standard_quantity


class GroceryService(BaseService):
    def __init__(self, repos: AllRepositories, user_id: UUID) -> None:
        super().__init__()
        self.repos = repos
        self.user_id = user_id
        self.weeks = repos.grocery_weeks
        # Apply strict compatibility even while building a single recipe, before week metadata is attached.
        self.shopping = ShoppingListService(repos, strict_units=True)

    def validate_food(self, food_id: UUID) -> IngredientFood:
        food = self.repos.ingredient_foods.get_one(food_id)
        if food is None:
            raise HTTPException(404, "Ingredient not found in your group")
        return food

    def save_product(self, data: GroceryProductCreate, product_id: UUID | None = None) -> GroceryProductOut:
        self.validate_food(data.food_id)
        if product_id and self.repos.grocery_products.get_one(product_id) is None:
            raise HTTPException(404, "Product not found")
        payload = data.cast(GroceryProductSave, group_id=self.repos.group_id, household_id=self.repos.household_id)
        if product_id:
            return self.repos.grocery_products.update(product_id, payload)
        return self.repos.grocery_products.create(payload)

    def save_rule(self, data: GroceryFoodRuleCreate, rule_id: UUID | None = None) -> GroceryFoodRuleOut:
        self.validate_food(data.food_id)
        if rule_id and self.repos.grocery_food_rules.get_one(rule_id) is None:
            raise HTTPException(404, "Rule not found")
        payload = data.cast(GroceryFoodRuleSave, group_id=self.repos.group_id, household_id=self.repos.household_id)
        try:
            if rule_id:
                return self.repos.grocery_food_rules.update(rule_id, payload)
            return self.repos.grocery_food_rules.create(payload)
        except IntegrityError as exc:
            self.repos.session.rollback()
            raise HTTPException(
                409, "This ingredient already has a rule of this kind. Edit that rule instead."
            ) from exc

    def meals(self, week_start: date) -> list[ReadPlanEntry]:
        end = week_start + timedelta(days=6)
        return self.repos.meals.page_all(
            PaginationQuery(
                per_page=-1,
                order_by="date",
                order_direction=OrderDirection.asc,
                query_filter=f'date >= "{week_start}" AND date <= "{end}"',
            )
        ).items

    def view(self, value: date, warnings: list[str] | None = None) -> GroceryWeekView:
        week_start = monday(value)
        week = self.weeks.get_by_date(week_start)
        result = GroceryWeekView(
            week_start=week_start,
            week=week,
            meals=self.meals(week_start),
            warnings=warnings if warnings is not None else (week.warnings if week else []),
        )
        if week is None:
            return result
        result.shopping_list = self.repos.group_shopping_lists.get_one(week.shopping_list_id)
        if result.shopping_list is None:
            return result
        products = self.repos.grocery_products.get_all()
        units = {unit.id: unit for unit in self.repos.ingredient_units.get_all()}
        grouped: dict[str, GroceryPurchaseOut] = {}
        for item in result.shopping_list.list_items:
            extras = item.extras or {}
            manual_store = extras.get(STORE_OVERRIDE)
            product = choose_product(products, item.food_id, week.stores, manual_store, extras.get(PRODUCT_OVERRIDE))
            store = manual_store or (product.store if product else None)
            checked_key = "checked" if item.checked else "pending"
            identity = str(product.id) if product else str(item.food_id or item.id)
            key = f"{checked_key}:{store or 'unassigned'}:{identity}"
            if key not in grouped:
                grouped[key] = GroceryPurchaseOut(
                    key=key,
                    food_name=item.food.name if item.food else item.note or "Grocery item",
                    store=store,
                    product=product,
                    items=[],
                )
            grouped[key].items.append(item)
        for purchase in grouped.values():
            product = purchase.product
            if not product or not product.package_quantity or not product.package_unit:
                continue
            total = 0.0
            # Running out of something without saying how much means buying at least one package
            at_least_one = False
            for item in purchase.items:
                if is_usual_amount(item):
                    at_least_one = True
                    continue
                amount = item_standard_amount(item, units)
                converted = convert_amount(*amount, product.package_unit) if amount else None
                if converted is None:
                    purchase.quantity_note = (
                        "Review package quantity: ingredient units are unspecified or incompatible."
                    )
                    break
                total += converted
            else:
                minimum = 1 if at_least_one else 0
                purchase.package_quantity_needed = round(total, 6) or minimum * product.package_quantity
                purchase.package_count = max(minimum, ceil(total / product.package_quantity - EPSILON))
        result.purchases = sorted(
            grouped.values(),
            key=lambda purchase: (purchase.items[0].checked, purchase.store or "zz", purchase.food_name.lower()),
        )
        return result

    def _consolidate(self, items: list[ShoppingListItemCreate]) -> list[ShoppingListItemCreate]:
        result: list[ShoppingListItemCreate] = []
        for item in items:
            item.extras = {SOURCE: "week"}
            for i, existing in enumerate(result):
                if self.shopping.can_merge(item, existing):
                    result[i] = self.shopping.merge_items(item, existing).cast(ShoppingListItemCreate)
                    break
            else:
                result.append(item)
        return result

    def _apply_rules(
        self, week: GroceryWeek, desired: list[ShoppingListItemCreate], skip_on_hand: bool, warnings: list[str]
    ) -> list[ShoppingListItemCreate]:
        list_id = week.shopping_list_id
        rules = [rule for rule in self.repos.grocery_food_rules.get_all() if rule.enabled]
        units = {unit.id: unit for unit in self.repos.ingredient_units.get_all()}
        current_pantry = {
            str(rule.food_id): rule.model_dump(mode="json") for rule in rules if rule.kind == GroceryRuleKind.pantry
        }
        existing_list = self.repos.group_shopping_lists.get_one(list_id)
        started_shopping = existing_list and any(item.checked for item in existing_list.list_items)
        if not started_shopping:
            week.pantry_snapshot = current_pantry
        elif current_pantry != week.pantry_snapshot:
            warnings.append(
                "Pantry changes apply to future weeks after shopping starts. "
                "This week keeps its starting stock to avoid counting purchases twice."
            )
        pantry = {
            UUID(food_id): GroceryFoodRuleOut.model_validate(raw) for food_id, raw in week.pantry_snapshot.items()
        }
        for rule in (rule for rule in rules if rule.kind == GroceryRuleKind.recurring and rule.quantity > 0):
            compatible: list[tuple[ShoppingListItemCreate, float]] = []
            for item in desired:
                if item.food_id != rule.food_id:
                    continue
                amount = item_standard_amount(item, units)
                converted = convert_amount(*amount, rule.unit) if amount else None
                if converted is not None:
                    compatible.append((item, converted))
            quantity = rule.quantity
            if rule.mode == "minimum":
                quantity = max(0.0, quantity - sum(amount for _, amount in compatible))
                if not compatible and any(item.food_id == rule.food_id for item in desired):
                    warnings.append(
                        f"{rule.food.name}: recurring target uses incompatible units; review the separate amounts."
                    )
            if quantity <= EPSILON:
                continue
            unit = self.weeks.standard_unit(rule.unit)
            if unit:
                units[unit.id] = unit
            desired.append(
                ShoppingListItemCreate(
                    shopping_list_id=list_id,
                    food_id=rule.food_id,
                    unit_id=unit.id if unit else None,
                    unit=unit,
                    quantity=quantity,
                    note="Weekly staple",
                    extras={SOURCE: "week"},
                )
            )
        desired = self._consolidate(desired)
        # Pantry is deducted once from the whole week's demand, including minimum recurring targets.
        for food_id, rule in pantry.items():
            remaining = rule.quantity
            for item in desired:
                if item.food_id != food_id or item.quantity <= 0:
                    continue
                item_amount = item_standard_amount(item, units)
                in_rule = convert_amount(*item_amount, rule.unit) if item_amount else None
                if in_rule is None:
                    warnings.append(
                        f"{rule.food.name}: pantry amount could not be converted; quantity left for manual review."
                    )
                    continue
                deduction = min(remaining, in_rule)
                in_item = amount_in_item_unit(deduction, rule.unit, item, units)
                if in_item is not None:
                    item.quantity = max(0.0, item.quantity - in_item)
                    if item.quantity <= EPSILON:
                        item.extras = {**(item.extras or {}), "shop.satisfied": "true"}
                    remaining -= deduction
                    self._scale_references(item, (in_rule - deduction) / in_rule if in_rule else 0)
        if skip_on_hand:
            household = self.repos.households.get_one(self.repos.household_id)
            foods = {food.id: food for food in self.repos.ingredient_foods.get_all()}
            desired = [
                item
                for item in desired
                if not (
                    item.food_id not in pantry
                    and item.food_id in foods
                    and household
                    and household.slug in foods[item.food_id].households_with_ingredient_food
                )
            ]
        return [item for item in desired if (item.extras or {}).get("shop.satisfied") != "true"]

    @staticmethod
    def _scale_references(item: ShoppingListItemCreate, factor: float) -> None:
        for ref in item.recipe_references:
            ref.recipe_quantity *= max(0.0, factor)

    def _desired_items(
        self, week: GroceryWeek, data: GroceryWeekGenerate, warnings: list[str]
    ) -> tuple[list[ShoppingListItemCreate], dict[UUID, float]]:
        meals = self.meals(week.week_start)
        valid_ids = {str(meal.id) for meal in meals}
        if set(data.meal_scales) - valid_ids:
            raise HTTPException(400, "A recipe multiplier refers to a meal outside this week")
        recipes = get_repositories(self.repos.session, group_id=self.repos.group_id, household_id=None).recipes.by_user(
            self.user_id
        )
        items: list[ShoppingListItemCreate] = []
        recipe_scales: dict[UUID, float] = defaultdict(float)
        for meal in meals:
            if not meal.recipe_id or meal.entry_type not in (PlanEntryType.dinner, PlanEntryType.side):
                continue
            scale = data.meal_scales.get(str(meal.id), 1.0)
            if scale <= 0:
                continue
            recipe = recipes.get_one(meal.recipe_id, key="id")
            if recipe is None:
                warnings.append(
                    f"{meal.title or 'A planned recipe'} is no longer available; its ingredients were skipped."
                )
                continue
            # Mealie's builder supplies unit-aware recipe references and nested recipe handling.
            items.extend(
                self.shopping.get_shopping_list_items_from_recipe(
                    week.shopping_list_id,
                    recipe.id,
                    scale,
                    recipe.recipe_ingredient,
                    skip_on_hand=False,
                )
            )
            recipe_scales[recipe.id] += scale
        desired = self._consolidate(items)
        if any(item.food_id is None for item in desired):
            warnings.append(
                "Some ingredients are not linked to foods. Link or parse them in the recipe editor "
                "so your preferred products can be selected."
            )
        desired = self._apply_rules(week, desired, data.skip_on_hand, warnings)
        return desired, dict(recipe_scales)

    def _same_demand(self, item1: ShoppingListItemBase, item2: ShoppingListItemBase) -> bool:
        # Override choices belong to the purchasing decision, not the identity of recipe demand.
        left = item1.cast(ShoppingListItemCreate, checked=False, extras={SOURCE: "week"})
        right = item2.cast(ShoppingListItemCreate, checked=False, extras={SOURCE: "week"})
        return self.shopping.can_merge(left, right)

    def _changes(
        self, desired: list[ShoppingListItemCreate], existing: list[ShoppingListItemOut]
    ) -> tuple[list[ShoppingListItemCreate], list[ShoppingListItemUpdateBulk], list[UUID]]:
        units = {unit.id: unit for unit in self.repos.ingredient_units.get_all()}
        generated = [item for item in existing if (item.extras or {}).get(SOURCE) == "week"]
        checked = [item for item in generated if item.checked]
        pending = [item for item in generated if not item.checked]
        used: set[UUID] = set()
        creates: list[ShoppingListItemCreate] = []
        updates: list[ShoppingListItemUpdateBulk] = []
        for item in desired:
            original_quantity = item.quantity
            matching_checked = [old for old in checked if self._same_demand(old, item)]
            if original_quantity <= EPSILON and matching_checked:
                continue
            for purchased in matching_checked:
                amount = item_standard_amount(purchased, units)
                extras = purchased.extras or {}
                try:
                    recorded = float(extras.get(PURCHASED_AMOUNT, ""))
                    recorded_unit = extras.get(PURCHASED_UNIT)
                    if isfinite(recorded) and recorded >= 0 and recorded_unit in {unit.value for unit in GroceryUnit}:
                        amount = recorded, recorded_unit
                except TypeError, ValueError:
                    pass
                deduction = amount_in_item_unit(*amount, item, units) if amount else None
                if deduction is None and purchased.unit_id == item.unit_id:
                    deduction = purchased.quantity
                if deduction is not None:
                    item.quantity = max(0.0, item.quantity - deduction)
            if original_quantity > 0 and item.quantity <= EPSILON:
                continue
            if original_quantity > 0:
                self._scale_references(item, item.quantity / original_quantity)
            matching = next((old for old in pending if old.id not in used and self._same_demand(old, item)), None)
            if matching:
                used.add(matching.id)
                updates.append(
                    item.cast(
                        ShoppingListItemUpdateBulk, id=matching.id, position=matching.position, extras=matching.extras
                    )
                )
            else:
                # Carry a trip's manual choice onto newly needed quantities of an already purchased ingredient.
                if matching_checked:
                    item.extras = dict(matching_checked[-1].extras or {SOURCE: "week"})
                    item.extras.pop(PURCHASED_AMOUNT, None)
                    item.extras.pop(PURCHASED_UNIT, None)
                creates.append(item)
        return creates, updates, [item.id for item in pending if item.id not in used]

    def generate(self, value: date, data: GroceryWeekGenerate) -> GroceryWeekView:
        warnings: list[str] = []
        try:
            week = self.weeks.prepare(monday(value), self.user_id, data.expected_revision, create=True)
            desired, recipe_scales = self._desired_items(week, data, warnings)
            current = self.repos.group_shopping_lists.get_one(week.shopping_list_id)
            creates, updates, deletes = self._changes(desired, current.list_items if current else [])
            self.weeks.reconcile(week, creates, updates, deletes, recipe_scales)
            self.weeks.initialize_labels(week, [label.id for label in self.repos.group_multi_purpose_labels.get_all()])
            week.stores = [store.value for store in data.stores]
            week.meal_scales = dict(data.meal_scales)
            week.skip_on_hand = data.skip_on_hand
            week.warnings = list(dict.fromkeys(warnings))
            self._sync_restock(reserved=week)
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.view(value, list(dict.fromkeys(warnings)))

    def assign(self, value: date, data: GroceryItemAssignment) -> GroceryWeekView:
        try:
            week = self.weeks.prepare(monday(value), self.user_id, data.expected_revision)
            items = self.weeks.item_models(week, data.item_ids)
            product = self.repos.grocery_products.get_one(data.product_id) if data.product_id else None
            if data.product_id and (product is None or not product.enabled):
                raise HTTPException(404, "Product not found or disabled")
            if product and any(item.food_id != product.food_id for item in items):
                raise HTTPException(400, "This product belongs to a different ingredient")
            if product and data.store and product.store != data.store:
                raise HTTPException(400, "The product and store do not match")
            for item in items:
                extras = {extra.key_name: extra.value for extra in item.extras}
                extras.pop(STORE_OVERRIDE, None)
                extras.pop(PRODUCT_OVERRIDE, None)
                if product:
                    extras[PRODUCT_OVERRIDE] = str(product.id)
                    extras[STORE_OVERRIDE] = product.store.value
                elif data.store:
                    extras[STORE_OVERRIDE] = data.store.value
                item.update(session=self.repos.session, extras=extras)
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.view(value)

    def check(self, value: date, data: GroceryItemCheck) -> GroceryWeekView:
        try:
            week = self.weeks.prepare(monday(value), self.user_id, data.expected_revision)
            items = self.weeks.item_models(week, data.item_ids)
            purchased_amounts = self._purchased_amounts(week, items) if data.checked else {}
            for item in items:
                item.checked = data.checked
                extras = {extra.key_name: extra.value for extra in item.extras}
                extras.pop(PURCHASED_AMOUNT, None)
                extras.pop(PURCHASED_UNIT, None)
                if item.id in purchased_amounts:
                    amount, unit = purchased_amounts[item.id]
                    extras[PURCHASED_AMOUNT] = str(amount)
                    extras[PURCHASED_UNIT] = unit
                item.update(session=self.repos.session, extras=extras)
            self._sync_restock(reserved=week)
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.view(value)

    def _purchased_amounts(self, week: GroceryWeek, models: list[ShoppingListItem]) -> dict[UUID, tuple[float, str]]:
        """Checking a suggested two-pack purchase records its package overage as bought stock."""
        products = self.repos.grocery_products.get_all()
        units = {unit.id: unit for unit in self.repos.ingredient_units.get_all()}
        groups: dict[UUID, list[tuple[ShoppingListItemOut, float]]] = defaultdict(list)
        selected_products: dict[UUID, GroceryProductOut] = {}
        for model in models:
            item = ShoppingListItemOut.model_validate(model)
            extras = item.extras or {}
            product = choose_product(
                products, item.food_id, week.stores, extras.get(STORE_OVERRIDE), extras.get(PRODUCT_OVERRIDE)
            )
            if not product or not product.package_quantity or not product.package_unit:
                continue
            standard_amount = item_standard_amount(item, units)
            converted = convert_amount(*standard_amount, product.package_unit) if standard_amount else None
            if converted is not None:
                selected_products[product.id] = product
                groups[product.id].append((item, converted))
        result: dict[UUID, tuple[float, str]] = {}
        for product_id, entries in groups.items():
            product = selected_products[product_id]
            total = sum(amount for _, amount in entries)
            assert product.package_quantity and product.package_unit
            overage = max(0.0, ceil(total / product.package_quantity - EPSILON) * product.package_quantity - total)
            for item, amount in entries:
                if (item.extras or {}).get(SOURCE) != "week":
                    continue
                result[item.id] = amount + overage, product.package_unit.value
                overage = 0.0
        return result

    def add_manual(self, value: date, data: GroceryManualItemCreate) -> GroceryWeekView:
        try:
            food = self.validate_food(data.food_id) if data.food_id else None
            week = self.weeks.prepare(monday(value), self.user_id, data.expected_revision)
            unit = self.weeks.standard_unit(data.unit)
            extras = {SOURCE: "manual"}
            if data.store:
                extras[STORE_OVERRIDE] = data.store.value
            item = ShoppingListItem(
                session=self.repos.session,
                shopping_list_id=week.shopping_list_id,
                food_id=food.id if food else None,
                label_id=food.label_id if food else None,
                note=data.note,
                quantity=data.quantity,
                unit_id=unit.id if unit else None,
                extras=extras,
                checked=False,
                position=len(self.weeks.list_model(week).list_items),
            )
            self.repos.session.add(item)
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.view(value)

    def delete_manual(self, value: date, data: GroceryItemDelete) -> GroceryWeekView:
        try:
            week = self.weeks.prepare(monday(value), self.user_id, data.expected_revision)
            items = self.weeks.item_models(week, data.item_ids)
            if any({extra.key_name: extra.value for extra in item.extras}.get(SOURCE) == "week" for item in items):
                raise HTTPException(400, "Change the meal plan or pantry to remove generated ingredients")
            for item in items:
                self.repos.session.delete(item)
            # Out of items deleted here are off the Out of list too
            self._sync_restock(reserved=week)
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.view(value)

    # ------------------------------------------------------------------
    # Common items: the ingredients the household has saved products for. The picker adds them
    # through the Out of list, so they follow its rules.

    def common_items(self) -> GroceryCommonItemList:
        """
        The ingredients the household has enabled products for, to add to the grocery list in one tap.
        Each one's products start with the one the list new items go on would buy.
        """
        target = self.weeks.newest_from(monday(household_today()))
        stores = list(target.stores) if target and target.stores else [store.value for store in GroceryStore]
        order = {store: i for i, store in enumerate(stores)}
        by_food: dict[UUID, list[GroceryProductOut]] = defaultdict(list)
        for product in self.repos.grocery_products.get_all():
            if product.enabled:
                by_food[product.food_id].append(product)
        listed: set[UUID] = set()
        shopping_list = self.repos.group_shopping_lists.get_one(target.shopping_list_id) if target else None
        for item in shopping_list.list_items if shopping_list else []:
            # Out of items are left to the Out of list, which the picker reads itself
            if item.food_id and not item.checked and (item.extras or {}).get(SOURCE) != "restock":
                listed.add(item.food_id)
        aisles = self.weeks.food_aisles(set(by_food))
        items = [
            GroceryCommonItemOut(
                food=products[0].food,
                aisle=aisles.get(food_id),
                # The order choose_product uses, with stores the week isn't visiting last
                products=sorted(
                    products,
                    key=lambda product: (
                        product.store not in order,
                        product.priority,
                        order.get(product.store, 99),
                        product.name.lower(),
                        str(product.id),
                    ),
                ),
                listed=food_id in listed,
            )
            for food_id, products in by_food.items()
        ]
        items.sort(key=lambda item: (item.food.name.lower(), str(item.food.id)))
        return GroceryCommonItemList(
            items=items,
            next_list_week=target.week_start if target else None,
            stores=[GroceryStore(store) for store in target.stores] if target else [],
        )

    # ------------------------------------------------------------------
    # The Out of list: things the household has run out of, recipe or no recipe. Each one rides on
    # the newest grocery list for this week or later until someone checks it off. With no such list
    # yet, it waits and joins the next one that's made.

    def restock_list(self) -> GroceryRestockList:
        try:
            if self._sync_restock():
                self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        current = monday(household_today())
        target = self.weeks.newest_from(current)
        restock = self.repos.grocery_restock_items
        return GroceryRestockList(
            items=[self.restock_out(item, current) for item in restock.open_models()],
            recently_bought=[
                self.restock_out(item, current) for item in restock.bought_models(get_utc_now() - RESTOCK_RECENT)
            ],
            next_list_week=target.week_start if target else None,
        )

    def restock_out(self, item: GroceryRestockItem, current: date | None = None) -> GroceryRestockOut:
        result = GroceryRestockOut.model_validate(item)
        current = current or monday(household_today())
        if result.bought_at:
            result.status = GroceryRestockStatus.bought
        elif result.shopping_list_item_id and result.week_start and result.week_start >= current:
            result.status = GroceryRestockStatus.listed
        return result

    def add_restock(self, data: GroceryRestockCreate, added_by: str = "") -> tuple[GroceryRestockOut, bool]:
        """
        Put something on the Out of list. Running out of something that's already listed fills in
        whatever new details were given instead of listing it twice. Returns the item, and whether
        it's new.
        """
        try:
            food_id = self._restock_food_id(data)
            item = self._open_restock(data.name, food_id)
            created = item is None
            if item is None:
                item = GroceryRestockItem(
                    session=self.repos.session,
                    group_id=self.repos.group_id,
                    household_id=self.repos.household_id,
                    name=data.name,
                    food_id=food_id,
                    quantity=data.quantity,
                    unit=data.unit.value if data.unit else None,
                    store=data.store.value if data.store else None,
                    note=data.note,
                    added_by=added_by,
                )
                self.repos.session.add(item)
            else:
                if data.quantity is not None:
                    item.quantity = data.quantity
                    item.unit = data.unit.value if data.unit else None
                if data.store:
                    item.store = data.store.value
                if data.note:
                    item.note = data.note
                if food_id and not item.food_id:
                    item.food_id = food_id
                self._refresh_restock_row(item)
            self._sync_restock()
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.restock_out(item), created

    def update_restock(self, item_id: UUID, data: GroceryRestockCreate) -> GroceryRestockOut:
        try:
            item = self.repos.grocery_restock_items.item_model(item_id)
            item.name = data.name
            item.food_id = self._restock_food_id(data)
            item.quantity = data.quantity
            item.unit = data.unit.value if data.unit else None
            item.store = data.store.value if data.store else None
            item.note = data.note
            if item.bought_at is None:
                self._refresh_restock_row(item)
            self._sync_restock()
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.restock_out(item)

    def remove_restock(self, item_id: UUID) -> GroceryRestockOut:
        """Take something off the Out of list, and off the grocery list too unless it was bought there"""
        try:
            item = self.repos.grocery_restock_items.item_model(item_id)
            removed = self.restock_out(item)
            row, week = self._restock_row_of(item)
            if row is not None and week is not None and not row.checked:
                self.repos.session.delete(row)
                self.weeks.bump({week.id})
            self.repos.session.delete(item)
            self._sync_restock()
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return removed

    def set_restock_bought(self, item_id: UUID, bought: bool) -> GroceryRestockOut:
        """Check an item off (or back on), along with its row on the grocery list"""
        try:
            item = self.repos.grocery_restock_items.item_model(item_id)
            row, week = self._restock_row_of(item)
            if row is not None and week is not None and bool(row.checked) != bought:
                row.checked = bought
                self.weeks.bump({week.id})
            if bought and item.bought_at is None:
                item.bought_at = get_utc_now()
            elif not bought:
                item.bought_at = None
            self._sync_restock()
            self.weeks.commit()
        except Exception:
            self.repos.session.rollback()
            raise
        return self.restock_out(item)

    def _restock_food_id(self, data: GroceryRestockCreate) -> UUID | None:
        if data.food_id:
            return self.validate_food(data.food_id).id
        food = self.repos.grocery_restock_items.food_named(data.name)
        return food.id if food else None

    def _open_restock(self, name: str, food_id: UUID | None) -> GroceryRestockItem | None:
        normalized = GroceryRestockItem.normalize(name)
        for item in self.repos.grocery_restock_items.open_models():
            if (food_id and item.food_id == food_id) or GroceryRestockItem.normalize(item.name) == normalized:
                return item
        return None

    def _restock_row_of(self, item: GroceryRestockItem) -> tuple[ShoppingListItem | None, GroceryWeek | None]:
        if not item.shopping_list_item_id:
            return None, None
        return self.weeks.list_items({item.shopping_list_item_id}).get(item.shopping_list_item_id, (None, None))

    def _restock_row_fields(self, item: GroceryRestockItem) -> dict:
        """What an Out of item looks like as a row on the grocery list"""
        food = self.repos.ingredient_foods.get_one(item.food_id) if item.food_id else None
        unit = self.weeks.standard_unit(item.unit) if item.quantity and item.unit else None
        extras = {SOURCE: "restock", RESTOCK_ID: str(item.id)}
        if item.store:
            extras[STORE_OVERRIDE] = item.store
        if food:
            note = item.note
        else:
            note = f"{item.name} ({item.note})" if item.note else item.name
        return {
            "food_id": food.id if food else None,
            "label_id": food.label_id if food else None,
            "note": note,
            "quantity": item.quantity or 0,
            "unit_id": unit.id if unit else None,
            "extras": extras,
        }

    def _refresh_restock_row(self, item: GroceryRestockItem) -> None:
        """Carry edited details over to the item's row, if it hasn't been checked off yet"""
        row, week = self._restock_row_of(item)
        if row is not None and week is not None and not row.checked:
            row.update(session=self.repos.session, **self._restock_row_fields(item))
            self.weeks.bump({week.id})

    def _sync_restock(self, reserved: GroceryWeek | None = None) -> bool:
        """
        Bring the Out of list and the grocery lists in step, without committing. Returns whether
        anything changed. `reserved` is a week whose revision the caller has already claimed.

        A row checked off on a list marks its item bought, and unchecking the row reopens it. A row
        deleted from a list that still exists takes its item off the Out of list; if the whole list
        is gone, the item waits for the next one. Everything still needed goes on the newest list
        for this week or later, moving off any older list where it wasn't bought.
        """
        session = self.repos.session
        restock = self.repos.grocery_restock_items
        session.flush()
        now = get_utc_now()
        changed = restock.prune_bought(now - RESTOCK_KEEP)
        touched: set[UUID] = set()

        linked = restock.linked_models()
        rows = self.weeks.list_items({item.shopping_list_item_id for item in linked if item.shopping_list_item_id})
        weeks = self.weeks.week_models({item.week_start for item in linked if item.week_start})
        for item in linked:
            found = rows.get(item.shopping_list_item_id) if item.shopping_list_item_id else None
            if found is None:
                if item.bought_at is None and item.week_start in weeks:
                    session.delete(item)
                else:
                    item.shopping_list_item_id = None
                    if item.bought_at is None:
                        item.week_start = None
                changed = True
                continue
            row, week = found
            if item.week_start != week.week_start:
                item.week_start = week.week_start
                changed = True
            if row.checked and item.bought_at is None:
                item.bought_at = now
                changed = True
            elif not row.checked and item.bought_at is not None:
                item.bought_at = None
                changed = True
        session.flush()

        target = self.weeks.newest_from(monday(household_today()))
        if target is not None:
            position = self.weeks.next_position(target)
            for item in restock.open_models():
                found = rows.get(item.shopping_list_item_id) if item.shopping_list_item_id else None
                if found is not None:
                    row, week = found
                    if week.id == target.id:
                        continue
                    row.shopping_list_id = target.shopping_list_id
                    row.position = position
                    touched |= {week.id, target.id}
                else:
                    row = ShoppingListItem(
                        session=session,
                        shopping_list_id=target.shopping_list_id,
                        checked=False,
                        position=position,
                        **self._restock_row_fields(item),
                    )
                    session.add(row)
                    session.flush()
                    item.shopping_list_item_id = row.id
                    touched.add(target.id)
                position += 1
                item.week_start = target.week_start
                changed = True

        if reserved is not None:
            touched.discard(reserved.id)
        self.weeks.bump(touched)
        session.flush()
        return changed or bool(touched)

    def suggestions(self, plan_date: date, limit: int = 5) -> list[GrocerySuggestionOut]:
        rules = self.repos.group_meal_plan_rules.get_rules(PlanRulesDay.from_date(plan_date), PlanRulesType.dinner)
        query_filter = QueryFilterBuilder.combine_filters(*[rule.query_filter_string for rule in rules])
        recipes = get_repositories(self.repos.session, group_id=self.repos.group_id, household_id=None).recipes.by_user(
            self.user_id
        )
        candidates = recipes.page_all(PaginationQuery(per_page=-1, query_filter=query_filter)).items
        history = self.repos.meals.page_all(PaginationQuery(per_page=-1, query_filter=f'date < "{plan_date}"')).items
        last_planned: dict[UUID, date] = {}
        for meal in history:
            if meal.recipe_id:
                last_planned[meal.recipe_id] = max(last_planned.get(meal.recipe_id, date.min), meal.date)
        already_planned = {meal.recipe_id for meal in self.meals(monday(plan_date)) if meal.recipe_id}
        household = self.repos.households.get_one(self.repos.household_id)
        on_hand = {
            food.id
            for food in self.repos.ingredient_foods.get_all()
            if household and household.slug in food.households_with_ingredient_food
        }
        recipe_foods = self.weeks.recipe_food_ids([recipe.id for recipe in candidates if recipe.id]) if on_hand else {}
        result: list[GrocerySuggestionOut] = []
        for recipe in candidates:
            if recipe.id in already_planned:
                continue
            last = last_planned.get(recipe.id)
            days = (plan_date - last).days if last else 42
            reasons = [f"Not planned for {days} days" if last else "Not in your recent meal plans"]
            rating = recipe.rating or 0
            score = min(days / 42, 1) * 40 + rating * 4
            if rating >= 4:
                reasons.append("Highly rated")
            food_ids = recipe_foods.get(recipe.id, set()) if recipe.id else set()
            overlap = len(food_ids & on_hand)
            if overlap:
                score += 15 * overlap / max(1, len(food_ids))
                reasons.append(f"Uses {overlap} ingredient{'s' if overlap != 1 else ''} on hand")
            result.append(
                GrocerySuggestionOut(recipe=recipe.cast(RecipeSummary), score=round(score, 2), reasons=reasons)
            )
        return sorted(result, key=lambda suggestion: (-suggestion.score, suggestion.recipe.name or ""))[:limit]
