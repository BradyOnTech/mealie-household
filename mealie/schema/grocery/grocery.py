from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import UUID4, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.grocery import GroceryFoodRule, GroceryProduct
from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.household.group_shopping_list import ShoppingListItemOut, ShoppingListOut
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.schema.recipe.recipe_ingredient import IngredientFoodSummary


class GroceryStore(StrEnum):
    walmart = "walmart"
    cub = "cub"
    aldi = "aldi"
    whole_foods = "whole_foods"


class GroceryUnit(StrEnum):
    COUNT = "count"
    gram = "gram"
    kilogram = "kilogram"
    ounce = "ounce"
    pound = "pound"
    milliliter = "milliliter"
    liter = "liter"
    fluid_ounce = "fluid_ounce"
    cup = "cup"


class GroceryRuleKind(StrEnum):
    pantry = "pantry"
    recurring = "recurring"


class GroceryRecurringMode(StrEnum):
    minimum = "minimum"
    extra = "extra"


class GroceryProductCreate(MealieModel):
    food_id: UUID4
    name: str = Field(min_length=1, max_length=255)
    store: GroceryStore
    url: str | None = Field(default=None, max_length=4000)
    priority: int = Field(default=0, ge=0, le=10000)
    enabled: bool = True
    package_quantity: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    package_unit: GroceryUnit | None = None
    notes: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Product name is required")
        return value.strip()

    @field_validator("url")
    @classmethod
    def validate_product_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        url = TypeAdapter(HttpUrl).validate_python(value.strip())
        if url.scheme != "https" or url.username or url.password:
            raise ValueError("Use an HTTPS product link without embedded credentials")
        return str(url)

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        if (self.package_quantity is None) != (self.package_unit is None):
            raise ValueError("Set both package size and package unit, or leave both empty")
        return self


class GroceryProductSave(GroceryProductCreate):
    group_id: UUID4
    household_id: UUID4


class GroceryProductOut(GroceryProductSave):
    id: UUID4
    food: IngredientFoodSummary
    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [selectinload(GroceryProduct.food)]


class GroceryFoodRuleCreate(MealieModel):
    food_id: UUID4
    kind: GroceryRuleKind
    quantity: float = Field(ge=0, allow_inf_nan=False)
    unit: GroceryUnit
    mode: GroceryRecurringMode = GroceryRecurringMode.minimum
    enabled: bool = True


class GroceryFoodRuleSave(GroceryFoodRuleCreate):
    group_id: UUID4
    household_id: UUID4


class GroceryFoodRuleOut(GroceryFoodRuleSave):
    id: UUID4
    food: IngredientFoodSummary
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [selectinload(GroceryFoodRule.food)]


class GroceryWeekOut(MealieModel):
    id: UUID4
    group_id: UUID4
    household_id: UUID4
    week_start: date
    shopping_list_id: UUID4
    stores: list[GroceryStore]
    meal_scales: dict[str, float]
    revision: int
    skip_on_hand: bool
    warnings: list[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class GroceryWeekGenerate(MealieModel):
    stores: list[GroceryStore] = Field(min_length=1, max_length=4)
    meal_scales: dict[str, float] = Field(default_factory=dict)
    skip_on_hand: bool = True
    expected_revision: int = Field(default=0, ge=0)

    @field_validator("stores")
    @classmethod
    def unique_stores(cls, value: list[GroceryStore]) -> list[GroceryStore]:
        return list(dict.fromkeys(value))

    @field_validator("meal_scales")
    @classmethod
    def validate_scales(cls, value: dict[str, float]) -> dict[str, float]:
        from math import isfinite

        if any(not isfinite(scale) or not 0 <= scale <= 100 for scale in value.values()):
            raise ValueError("Recipe multipliers must be between 0 and 100")
        return value


class GroceryPurchaseOut(MealieModel):
    key: str
    food_name: str
    store: GroceryStore | None
    product: GroceryProductOut | None
    items: list[ShoppingListItemOut]
    package_count: int | None = None
    package_quantity_needed: float | None = None
    quantity_note: str = ""


class GroceryWeekView(MealieModel):
    week_start: date
    week: GroceryWeekOut | None = None
    shopping_list: ShoppingListOut | None = None
    meals: list[ReadPlanEntry] = Field(default_factory=list)
    purchases: list[GroceryPurchaseOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GroceryItemAssignment(MealieModel):
    item_ids: list[UUID4] = Field(min_length=1, max_length=100)
    store: GroceryStore | None = None
    product_id: UUID4 | None = None
    expected_revision: int = Field(ge=0)


class GroceryItemCheck(MealieModel):
    item_ids: list[UUID4] = Field(min_length=1, max_length=100)
    checked: bool
    expected_revision: int = Field(ge=0)


class GroceryManualItemCreate(MealieModel):
    food_id: UUID4 | None = None
    note: str = Field(default="", max_length=2000)
    quantity: float = Field(default=1, gt=0, allow_inf_nan=False)
    unit: GroceryUnit = GroceryUnit.COUNT
    store: GroceryStore | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def food_or_note(self) -> Self:
        if not self.food_id and not self.note.strip():
            raise ValueError("Choose an ingredient or enter an item name")
        return self


class GrocerySuggestionOut(MealieModel):
    recipe: RecipeSummary
    score: float
    reasons: list[str]


class GroceryItemDelete(MealieModel):
    item_ids: list[UUID4] = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)
