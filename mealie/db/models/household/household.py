from typing import TYPE_CHECKING

import sqlalchemy as sa
import sqlalchemy.orm as orm
from pydantic import ConfigDict
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID
from ..recipe.ingredient import households_to_ingredient_foods
from ..recipe.tool import households_to_tools
from .household_to_recipe import HouseholdToRecipe

if TYPE_CHECKING:
    from ..group import Group
    from ..recipe import IngredientFoodModel, RecipeModel, Tool
    from ..users import User
    from . import (
        CookBook,
        GroupEventNotifierModel,
        GroupInviteToken,
        GroupRecipeAction,
        GroupWebhooksModel,
        HouseholdPreferencesModel,
    )
    from .grocery import GroceryFoodRule, GroceryProduct, GroceryRestockItem, GroceryWeek
    from .messages import HouseholdMessage


class Household(SqlAlchemyBase, BaseMixins):
    __tablename__ = "households"
    __table_args__ = (
        sa.UniqueConstraint("group_id", "name", name="household_name_group_id_key"),
        sa.UniqueConstraint("group_id", "slug", name="household_slug_group_id_key"),
    )

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    name: FilterableColumn[str] = mapped_column(sa.String, index=True, nullable=False)
    slug: FilterableColumn[str | None] = mapped_column(sa.String, index=True)

    invite_tokens: Mapped[list[GroupInviteToken]] = orm.relationship(
        "GroupInviteToken", back_populates="household", cascade="all, delete-orphan"
    )
    preferences: Mapped[HouseholdPreferencesModel] = orm.relationship(
        "HouseholdPreferencesModel",
        back_populates="household",
        uselist=False,
        single_parent=True,
        cascade="all, delete-orphan",
    )

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    group: Mapped[Group] = orm.relationship("Group", back_populates="households")
    users: Mapped[list[User]] = orm.relationship("User", back_populates="household")

    COMMON_ARGS = {
        "back_populates": "household",
        "cascade": "all, delete-orphan",
        "single_parent": True,
    }

    grocery_products: Mapped[list[GroceryProduct]] = orm.relationship("GroceryProduct", **COMMON_ARGS)
    grocery_food_rules: Mapped[list[GroceryFoodRule]] = orm.relationship("GroceryFoodRule", **COMMON_ARGS)
    grocery_weeks: Mapped[list[GroceryWeek]] = orm.relationship("GroceryWeek", **COMMON_ARGS)
    grocery_restock_items: Mapped[list[GroceryRestockItem]] = orm.relationship("GroceryRestockItem", **COMMON_ARGS)
    household_messages: Mapped[list[HouseholdMessage]] = orm.relationship("HouseholdMessage", **COMMON_ARGS)

    recipe_actions: Mapped[list[GroupRecipeAction]] = orm.relationship("GroupRecipeAction", **COMMON_ARGS)
    cookbooks: Mapped[list[CookBook]] = orm.relationship("CookBook", **COMMON_ARGS)

    webhooks: Mapped[list[GroupWebhooksModel]] = orm.relationship("GroupWebhooksModel", **COMMON_ARGS)
    group_event_notifiers: Mapped[list[GroupEventNotifierModel]] = orm.relationship(
        "GroupEventNotifierModel", **COMMON_ARGS
    )

    made_recipes: Mapped[list[RecipeModel]] = orm.relationship(
        "RecipeModel", secondary=HouseholdToRecipe.__tablename__, back_populates="made_by"
    )
    ingredient_foods_on_hand: Mapped[list[IngredientFoodModel]] = orm.relationship(
        "IngredientFoodModel",
        secondary=households_to_ingredient_foods,
        back_populates="households_with_ingredient_food",
    )
    tools_on_hand: Mapped[list[Tool]] = orm.relationship(
        "Tool", secondary=households_to_tools, back_populates="households_with_tool"
    )

    model_config = ConfigDict(
        exclude={
            "users",
            "webhooks",
            "recipe_actions",
            "cookbooks",
            "preferences",
            "invite_tokens",
            "group_event_notifiers",
            "group",
            "made_recipes",
        }
    )

    @auto_init()
    def __init__(self, **_) -> None:
        pass
