from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from mealie.db.models.household.grocery import GroceryRestockItem, GroceryWeek
from mealie.db.models.household.shopping_list import (
    ShoppingList,
    ShoppingListItem,
    ShoppingListMultiPurposeLabel,
    ShoppingListRecipeReference,
)
from mealie.db.models.recipe.ingredient import (
    IngredientFoodAliasModel,
    IngredientFoodModel,
    IngredientUnitModel,
    RecipeIngredientModel,
)
from mealie.db.models.recipe.labels import MultiPurposeLabel
from mealie.schema.grocery.grocery import GroceryRestockOut, GroceryWeekOut
from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListItemUpdateBulk
from mealie.schema.recipe.recipe_ingredient import IngredientUnit

from .repository_generic import HouseholdRepositoryGeneric

GROCERY_UNIT_ABBREVIATIONS = {
    "gram": ("g", "g"),
    "kilogram": ("kg", "kg"),
    "ounce": ("oz", "oz"),
    "pound": ("lb", "lb"),
    "milliliter": ("ml", "ml"),
    "liter": ("l", "l"),
    "fluid_ounce": ("fl oz", "fl oz"),
    "cup": ("cup", "cups"),
}
"""How a unit the grocery list had to create reads on the list, singular and plural"""


class RepositoryGroceryWeek(HouseholdRepositoryGeneric[GroceryWeekOut, GroceryWeek]):
    def recipe_food_ids(self, recipe_ids: list[UUID]) -> dict[UUID, set[UUID]]:
        """Read ingredients for an already access-filtered set of candidate recipes in one query."""
        result: dict[UUID, set[UUID]] = {}
        if not recipe_ids:
            return result
        rows = self.session.execute(
            select(RecipeIngredientModel.recipe_id, RecipeIngredientModel.food_id).where(
                RecipeIngredientModel.recipe_id.in_(recipe_ids), RecipeIngredientModel.food_id.is_not(None)
            )
        )
        for recipe_id, food_id in rows:
            result.setdefault(recipe_id, set()).add(food_id)
        return result

    def food_aisles(self, food_ids: set[UUID]) -> dict[UUID, str]:
        """The aisle of each of these foods that has one, which is its label, as on the grocery list"""
        if not food_ids:
            return {}
        rows = self.session.execute(
            select(IngredientFoodModel.id, MultiPurposeLabel.name)
            .join(MultiPurposeLabel, MultiPurposeLabel.id == IngredientFoodModel.label_id)
            .where(IngredientFoodModel.id.in_(food_ids), IngredientFoodModel.group_id == self.group_id)
        )
        return dict(rows.tuples().all())

    def standard_unit(self, name: str) -> IngredientUnit | None:
        if name == "count":
            return None
        unit = (
            self.session.execute(
                select(IngredientUnitModel).where(
                    IngredientUnitModel.group_id == self.group_id,
                    IngredientUnitModel.standard_unit == name,
                    IngredientUnitModel.standard_quantity == 1,
                )
            )
            .scalars()
            .first()
        )
        if unit is None:
            abbreviation, plural_abbreviation = GROCERY_UNIT_ABBREVIATIONS.get(name, (name, name))
            unit = IngredientUnitModel(
                session=self.session,
                group_id=self.group_id,
                name=f"Grocery: {name}",
                abbreviation=abbreviation,
                plural_abbreviation=plural_abbreviation,
                use_abbreviation=True,
                standard_quantity=1,
                standard_unit=name,
                fraction=False,
            )
            self.session.add(unit)
            self.session.flush()
        return IngredientUnit.model_validate(unit)

    def get_by_date(self, week_start: date) -> GroceryWeekOut | None:
        return self.get_one(week_start, key="week_start")  # type: ignore[arg-type]

    def prepare(self, week_start: date, user_id: UUID, expected_revision: int, *, create: bool = False) -> GroceryWeek:
        """Reserve one revision before editing. A single commit publishes the list and its week together."""
        query = select(GroceryWeek).filter_by(**self._filter_builder(week_start=week_start)).with_for_update()
        week = self.session.execute(query).scalar_one_or_none()
        if week is None:
            if not create:
                raise HTTPException(404, "Generate this week's grocery list first")
            if expected_revision != 0:
                raise HTTPException(409, "The week changed. Refresh and try again.")
            shopping_list = ShoppingList(
                session=self.session,
                group_id=self.group_id,
                user_id=user_id,
                name=f"Groceries · {week_start.isoformat()}",
                extras={"shop.week": week_start.isoformat()},
            )
            self.session.add(shopping_list)
            self.session.flush()
            week = GroceryWeek(
                session=self.session,
                group_id=self.group_id,
                household_id=self.household_id,
                week_start=week_start,
                shopping_list_id=shopping_list.id,
                stores=[],
                meal_scales={},
                skip_on_hand=True,
                revision=1,
            )
            self.session.add(week)
            try:
                self.session.flush()
            except IntegrityError as exc:
                self.session.rollback()
                raise HTTPException(409, "Another household member created this week. Refresh and try again.") from exc
            return week

        # The compare-and-set also acquires a write lock on SQLite, where SELECT FOR UPDATE is ignored.
        reserved = self.session.execute(
            update(GroceryWeek)
            .where(GroceryWeek.id == week.id, GroceryWeek.revision == expected_revision)
            .values(revision=expected_revision + 1)
            .returning(GroceryWeek.id)
        ).scalar_one_or_none()
        if reserved is None:
            self.session.rollback()
            raise HTTPException(409, "Another household member updated the list. Refresh and try again.")
        self.session.refresh(week)
        return week

    def list_model(self, week: GroceryWeek) -> ShoppingList:
        query = select(ShoppingList).filter_by(**self._filter_builder(id=week.shopping_list_id))
        return self.session.execute(query).scalar_one()

    def reconcile(
        self,
        week: GroceryWeek,
        create_items: list[ShoppingListItemCreate],
        update_items: list[ShoppingListItemUpdateBulk],
        delete_ids: list[UUID],
        recipe_scales: dict[UUID, float],
    ) -> None:
        shopping_list = self.list_model(week)
        by_id = {item.id: item for item in shopping_list.list_items}
        for item in update_items:
            by_id[item.id].update(session=self.session, **item.model_dump(exclude={"food", "unit", "display"}))
        for item_id in delete_ids:
            self.session.delete(by_id[item_id])
        for item in create_items:
            model = ShoppingListItem(session=self.session, **item.model_dump(exclude={"food", "unit", "display"}))
            shopping_list.list_items.append(model)
        shopping_list.recipe_references = [
            ShoppingListRecipeReference(session=self.session, recipe_id=recipe_id, recipe_quantity=scale)
            for recipe_id, scale in recipe_scales.items()
        ]
        self.session.flush()

    def initialize_labels(self, week: GroceryWeek, label_ids: list[UUID]) -> None:
        shopping_list = self.list_model(week)
        if not shopping_list.label_settings:
            shopping_list.label_settings = [
                ShoppingListMultiPurposeLabel(session=self.session, label_id=label_id, position=i)
                for i, label_id in enumerate(label_ids)
            ]

    def item_models(self, week: GroceryWeek, item_ids: list[UUID]) -> list[ShoppingListItem]:
        by_id = {item.id: item for item in self.list_model(week).list_items}
        if any(item_id not in by_id for item_id in item_ids):
            raise HTTPException(404, "A grocery item was not found in this household's list")
        return [by_id[item_id] for item_id in dict.fromkeys(item_ids)]

    def newest_from(self, week_start: date) -> GroceryWeek | None:
        """The household's list for the latest week on or after `week_start`"""
        query = (
            select(GroceryWeek)
            .filter_by(**self._filter_builder())
            .where(GroceryWeek.week_start >= week_start)
            .order_by(GroceryWeek.week_start.desc())
            .limit(1)
        )
        return self.session.execute(query).scalars().first()

    def week_models(self, week_starts: set[date]) -> dict[date, GroceryWeek]:
        if not week_starts:
            return {}
        query = select(GroceryWeek).filter_by(**self._filter_builder()).where(GroceryWeek.week_start.in_(week_starts))
        return {week.week_start: week for week in self.session.execute(query).scalars()}

    def list_items(self, item_ids: set[UUID]) -> dict[UUID, tuple[ShoppingListItem, GroceryWeek]]:
        """Rows on any of this household's weekly grocery lists, with the week each one is on"""
        if not item_ids:
            return {}
        query = (
            select(ShoppingListItem, GroceryWeek)
            .join(GroceryWeek, GroceryWeek.shopping_list_id == ShoppingListItem.shopping_list_id)
            .where(
                ShoppingListItem.id.in_(item_ids),
                GroceryWeek.group_id == self.group_id,
                GroceryWeek.household_id == self.household_id,
            )
        )
        return {item.id: (item, week) for item, week in self.session.execute(query).tuples()}

    def next_position(self, week: GroceryWeek) -> int:
        query = select(func.coalesce(func.max(ShoppingListItem.position), -1) + 1).where(
            ShoppingListItem.shopping_list_id == week.shopping_list_id
        )
        return int(self.session.execute(query).scalar_one())

    def bump(self, week_ids: set[UUID]) -> None:
        """Mark lists as changed, so a page still holding an older revision refreshes before it edits them"""
        if week_ids:
            self.session.execute(
                update(GroceryWeek).where(GroceryWeek.id.in_(week_ids)).values(revision=GroceryWeek.revision + 1)
            )

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise


class RepositoryGroceryRestock(HouseholdRepositoryGeneric[GroceryRestockOut, GroceryRestockItem]):
    def open_models(self) -> list[GroceryRestockItem]:
        query = (
            select(GroceryRestockItem)
            .filter_by(**self._filter_builder())
            .where(GroceryRestockItem.bought_at.is_(None))
            .order_by(GroceryRestockItem.created_at, GroceryRestockItem.name)
            .options(selectinload(GroceryRestockItem.food))
        )
        return list(self.session.execute(query).scalars())

    def bought_models(self, since: datetime, limit: int = 20) -> list[GroceryRestockItem]:
        query = (
            select(GroceryRestockItem)
            .filter_by(**self._filter_builder())
            .where(GroceryRestockItem.bought_at >= since)
            .order_by(GroceryRestockItem.bought_at.desc())
            .limit(limit)
            .options(selectinload(GroceryRestockItem.food))
        )
        return list(self.session.execute(query).scalars())

    def prune_bought(self, before: datetime) -> bool:
        """Forget items bought before `before`. Checks first, so a quiet read never takes a write lock."""
        scope = (
            GroceryRestockItem.group_id == self.group_id,
            GroceryRestockItem.household_id == self.household_id,
            GroceryRestockItem.bought_at < before,
        )
        if self.session.execute(select(GroceryRestockItem.id).where(*scope).limit(1)).first() is None:
            return False
        self.session.execute(delete(GroceryRestockItem).where(*scope))
        return True

    def linked_models(self) -> list[GroceryRestockItem]:
        """Everything standing in for a row on a grocery list, bought or not"""
        query = (
            select(GroceryRestockItem)
            .filter_by(**self._filter_builder())
            .where(GroceryRestockItem.shopping_list_item_id.is_not(None))
        )
        return list(self.session.execute(query).scalars())

    def item_model(self, item_id: UUID) -> GroceryRestockItem:
        query = select(GroceryRestockItem).filter_by(**self._filter_builder(id=item_id))
        item = self.session.execute(query).scalar_one_or_none()
        if item is None:
            raise HTTPException(404, "That item isn't on your Out of list")
        return item

    def food_named(self, name: str) -> IngredientFoodModel | None:
        """The group's food with exactly this name, plural, or alias, ignoring case and punctuation"""
        normalized = GroceryRestockItem.normalize(name)
        if not normalized:
            return None
        query = (
            select(IngredientFoodModel)
            .outerjoin(IngredientFoodAliasModel, IngredientFoodAliasModel.food_id == IngredientFoodModel.id)
            .where(IngredientFoodModel.group_id == self.group_id)
            .where(
                (IngredientFoodModel.name_normalized == normalized)
                | (IngredientFoodModel.plural_name_normalized == normalized)
                | (IngredientFoodAliasModel.name_normalized == normalized)
            )
            .order_by(IngredientFoodModel.name_normalized != normalized, IngredientFoodModel.created_at)
            .limit(1)
        )
        return self.session.execute(query).scalars().first()
