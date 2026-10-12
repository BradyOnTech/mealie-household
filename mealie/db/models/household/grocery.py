from datetime import date
from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealie.db.models._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from mealie.db.models._model_utils.auto_init import auto_init
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
