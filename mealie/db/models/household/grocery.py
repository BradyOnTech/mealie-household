from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealie.db.models._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from mealie.db.models._model_utils.auto_init import auto_init
from mealie.db.models._model_utils.datetime import NaiveDateTime
from mealie.db.models._model_utils.guid import GUID

if TYPE_CHECKING:
    from mealie.db.models.recipe.ingredient import IngredientFoodModel

    from .household import Household
    from .shopping_list import ShoppingList


class GroceryProduct(SqlAlchemyBase, BaseMixins):
    __tablename__ = "grocery_products"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = relationship("Household", back_populates="grocery_products")
    food_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("ingredient_foods.id"), nullable=False, index=True)
    food: Mapped[IngredientFoodModel] = relationship("IngredientFoodModel", back_populates="grocery_products")
    name: FilterableColumn[str] = mapped_column(String, nullable=False)
    store: FilterableColumn[str] = mapped_column(String, nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String)
    priority: FilterableColumn[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: FilterableColumn[bool] = mapped_column(Boolean, nullable=False, default=True)
    package_quantity: Mapped[float | None] = mapped_column(Float)
    package_unit: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String, nullable=False, default="")
    barcode: FilterableColumn[str | None] = mapped_column(String(14), index=True)
    """The package's barcode as a GTIN, so scanning the package finds the product"""

    model_config = ConfigDict(exclude={"food", "household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class GroceryFoodRule(SqlAlchemyBase, BaseMixins):
    __tablename__ = "grocery_food_rules"
    __table_args__ = (UniqueConstraint("household_id", "food_id", "kind", name="grocery_food_rule_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = relationship("Household", back_populates="grocery_food_rules")
    food_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("ingredient_foods.id"), nullable=False, index=True)
    food: Mapped[IngredientFoodModel] = relationship("IngredientFoodModel", back_populates="grocery_food_rules")
    kind: FilterableColumn[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="minimum")
    enabled: FilterableColumn[bool] = mapped_column(Boolean, nullable=False, default=True)

    model_config = ConfigDict(exclude={"food", "household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class GroceryWeek(SqlAlchemyBase, BaseMixins):
    __tablename__ = "grocery_weeks"
    __table_args__ = (UniqueConstraint("household_id", "week_start", name="grocery_week_household_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = relationship("Household", back_populates="grocery_weeks")
    week_start: FilterableColumn[date] = mapped_column(Date, nullable=False, index=True)
    shopping_list_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("shopping_lists.id"), nullable=False, unique=True)
    shopping_list: Mapped[ShoppingList] = relationship("ShoppingList", back_populates="grocery_week")
    stores: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    meal_scales: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skip_on_hand: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pantry_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    model_config = ConfigDict(exclude={"household", "shopping_list"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class GroceryRestockItem(SqlAlchemyBase, BaseMixins):
    """
    Something the household has run out of (the app's "Out of" list). It rides on the newest grocery
    list until someone checks it off, whether or not a recipe needs it.

    `shopping_list_item_id` points at the list row standing in for it, without a foreign key: that row
    belongs to the shopping list, and moves between weeks' lists or disappears without asking this one.
    """

    __tablename__ = "grocery_restock_items"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = relationship("Household", back_populates="grocery_restock_items")
    name: FilterableColumn[str] = mapped_column(String, nullable=False)
    food_id: FilterableColumn[GUID | None] = mapped_column(GUID, ForeignKey("ingredient_foods.id"), index=True)
    food: Mapped[IngredientFoodModel | None] = relationship(
        "IngredientFoodModel", back_populates="grocery_restock_items"
    )
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String)
    store: Mapped[str | None] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    added_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    shopping_list_item_id: Mapped[GUID | None] = mapped_column(GUID, index=True)
    week_start: Mapped[date | None] = mapped_column(Date)
    bought_at: FilterableColumn[datetime | None] = mapped_column(NaiveDateTime, index=True)

    model_config = ConfigDict(exclude={"food", "household"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass
