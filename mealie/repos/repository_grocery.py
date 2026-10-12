from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from mealie.db.models.household.grocery import GroceryWeek
from mealie.db.models.household.shopping_list import (
    ShoppingList,
    ShoppingListItem,
    ShoppingListMultiPurposeLabel,
    ShoppingListRecipeReference,
)
from mealie.db.models.recipe.ingredient import IngredientUnitModel, RecipeIngredientModel
from mealie.schema.grocery.grocery import GroceryWeekOut
from mealie.schema.household.group_shopping_list import ShoppingListItemCreate, ShoppingListItemUpdateBulk
from mealie.schema.recipe.recipe_ingredient import IngredientUnit

from .repository_generic import HouseholdRepositoryGeneric


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
            unit = IngredientUnitModel(
                session=self.session,
                group_id=self.group_id,
                name=f"Grocery: {name}",
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

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
