from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import UUID4, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.grocery import GroceryFoodRule, GroceryProduct, GroceryRestockItem
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


def https_product_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    url = TypeAdapter(HttpUrl).validate_python(value.strip())
    if url.scheme != "https" or url.username or url.password:
        raise ValueError("Use an HTTPS product link without embedded credentials")
    return str(url)


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
        return https_product_url(value)

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        if (self.package_quantity is None) != (self.package_unit is None):
            raise ValueError("Set both package size and package unit, or leave both empty")
        return self


class GroceryProductLookupRequest(MealieModel):
    url: str = Field(min_length=1, max_length=4000)

    @field_validator("url")
    @classmethod
    def validate_product_url(cls, value: str) -> str:
        url = https_product_url(value)
        if not url:
            raise ValueError("Paste a product link")
        return url


class GroceryProductLookup(MealieModel):
    """What a product's store link says about it, to fill in a new preferred product"""

    url: str
    name: str = ""
    store: GroceryStore | None = None
    package_quantity: float | None = None
    package_unit: GroceryUnit | None = None
    food: IngredientFoodSummary | None = None
    """The household's ingredient the product is"""
    new_food_name: str | None = None
    """When none of the household's ingredients fits, the one to add for the product"""
    read_with_ai: bool = False


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


class GroceryRestockStatus(StrEnum):
    waiting = "waiting"
    """Not on a grocery list yet. It joins the next list that's made."""
    listed = "listed"
    """On the newest grocery list, not bought yet"""
    bought = "bought"


class GroceryRestockCreate(MealieModel):
    """Something the household has run out of. An empty quantity means "the usual amount"."""

    name: str = Field(min_length=1, max_length=255)
    food_id: UUID4 | None = None
    """The ingredient this is. Found by name when it's left empty."""
    quantity: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    unit: GroceryUnit | None = None
    store: GroceryStore | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name what you're out of")
        return value

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def unit_needs_quantity(self) -> Self:
        if self.unit and self.quantity is None:
            raise ValueError("Enter an amount to go with the unit")
        return self


class GroceryRestockOut(GroceryRestockCreate):
    id: UUID4
    group_id: UUID4
    household_id: UUID4
    food: IngredientFoodSummary | None = None
    added_by: str = ""
    shopping_list_item_id: UUID4 | None = None
    week_start: date | None = None
    """The week of the grocery list it's on"""
    bought_at: datetime | None = None
    status: GroceryRestockStatus = GroceryRestockStatus.waiting
    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [selectinload(GroceryRestockItem.food)]


class GroceryRestockList(MealieModel):
    items: list[GroceryRestockOut] = Field(default_factory=list)
    """Still needed, oldest first"""
    recently_bought: list[GroceryRestockOut] = Field(default_factory=list)
    """Bought in the last two weeks, newest first"""
    next_list_week: date | None = None
    """The week of the list new items go on, or empty when they wait for the next list"""


class GroceryRestockBought(MealieModel):
    bought: bool = True


class GroceryCommonItemOut(MealieModel):
    """An ingredient the household has saved products for, which it can add to the list in one tap"""

    food: IngredientFoodSummary
    aisle: str | None = None
    """The ingredient's label, which is its aisle on the grocery list"""
    products: list[GroceryProductOut]
    """Its enabled products, starting with the one the list would buy"""
    listed: bool = False
    """
    Already on the list new items go on, for a recipe, a staple, or an addition, and not checked off.
    Out of items don't count here; they're on the Out of list.
    """


class GroceryCommonItemList(MealieModel):
    items: list[GroceryCommonItemOut] = Field(default_factory=list)
    """By ingredient name"""
    next_list_week: date | None = None
    """The week of the list new items go on, or empty when they wait for the next list"""
    stores: list[GroceryStore] = Field(default_factory=list)
    """The stores that list is shopping at"""
