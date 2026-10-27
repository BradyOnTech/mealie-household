"""
The household assistant: a chat about the household's food that can look things up and make
changes. Its tools go through the same services as the rest of the app, scoped to the household
of the person chatting.
"""

import datetime as dt
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mealie.core.exceptions import OpenAIServiceError
from mealie.db.models.household.grocery import GroceryRestockItem
from mealie.repos.all_repositories import AllRepositories, get_repositories
from mealie.schema.assistant.assistant import AssistantAction, AssistantChatResponse, AssistantMessage
from mealie.schema.grocery.grocery import (
    GroceryRestockCreate,
    GroceryRestockOut,
    GroceryRestockStatus,
    GroceryStore,
    GroceryUnit,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.response.pagination import OrderDirection, PaginationQuery
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.household_services.groceries import GroceryService, household_today, monday
from mealie.services.household_services.shop_extras import SOURCE
from mealie.services.openai.openai import (
    OpenAIChatMessage,
    OpenAIDataInjection,
    OpenAINotEnabledException,
    OpenAIService,
    OpenAITool,
    OpenAIToolError,
    tool_parameters,
)

MAX_HISTORY = 24
"""How many of the latest messages the model sees"""
MAX_RECIPE_TEXT = 6000

STORE_NAMES = {
    GroceryStore.walmart: "Walmart",
    GroceryStore.cub: "Cub Foods",
    GroceryStore.aldi: "Aldi",
    GroceryStore.whole_foods: "Whole Foods",
}


class _Args(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OutOfItemArgs(_Args):
    name: str = Field(description='What they\'re out of, named simply, like "rice" or "paper towels"')
    quantity: float | None = Field(None, description="How much to buy, only if they said. Leave empty otherwise.")
    unit: GroceryUnit | None = Field(None, description="The quantity's unit, if it has one")
    store: GroceryStore | None = Field(None, description="Where to buy it, only if they said")
    note: str | None = Field(None, description="Anything else they said about it, like a brand or size")


class AddOutOfItemsArgs(_Args):
    items: list[OutOfItemArgs] = Field(min_length=1, max_length=25)


class UpdateOutOfItemArgs(OutOfItemArgs):
    id: str = Field(description="The item's id, from get_out_of_list")


class OutOfItemIdsArgs(_Args):
    ids: list[str] = Field(min_length=1, max_length=25, description="Item ids, from get_out_of_list")


class MarkBoughtArgs(OutOfItemIdsArgs):
    bought: bool = Field(True, description="false puts a bought item back on the list")


class GroceryListArgs(_Args):
    week_of: dt.date | None = Field(
        None, description="Any day in the week whose list to read. Leave empty for the list they'll shop from next."
    )


class MealPlanArgs(_Args):
    start: dt.date | None = Field(None, description="First day to read; today if empty")
    end: dt.date | None = Field(None, description="Last day to read; six days after the start if empty")


class SearchRecipesArgs(_Args):
    query: str = Field(min_length=1, description="Words to look for in recipe names, descriptions and ingredients")
    limit: int = Field(8, ge=1, le=20)


class RecipeArgs(_Args):
    recipe: str = Field(description="The recipe's slug or id")


class SuggestDinnersArgs(_Args):
    day: dt.date = Field(description="The night to suggest dinner for")


class PlanMealArgs(_Args):
    day: dt.date
    meal: PlanEntryType = PlanEntryType.dinner
    recipe: str | None = Field(None, description="Slug or id of a saved recipe to plan")
    title: str | None = Field(None, description='What to plan when it isn\'t a saved recipe, like "Leftovers"')
    note: str | None = None


def short_day(day: dt.date) -> str:
    return f"{day:%a}, {day:%b} {day.day}"


def amount(quantity: float | None, unit: str | None) -> str | None:
    if not quantity:
        return None
    return f"{quantity:g} {unit}" if unit and unit != GroceryUnit.COUNT else f"{quantity:g}"


def http_message(error: HTTPException) -> str:
    detail = error.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


def validation_message(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(part) for part in e['loc']) or 'value'}: {e['msg']}" for e in error.errors())


class HouseholdAssistant(BaseService):
    def __init__(self, repos: AllRepositories, user: PrivateUser) -> None:
        super().__init__()
        self.repos = repos
        self.user = user
        self.groceries = GroceryService(repos, user.id)
        self.ai = OpenAIService(repos)
        self.actions: list[AssistantAction] = []

    @property
    def user_name(self) -> str:
        return self.user.full_name or self.user.username or ""

    async def reply(self, messages: list[AssistantMessage]) -> AssistantChatResponse:
        settings = self.ai.provider_settings
        if not (settings and settings.ai_enabled):
            raise OpenAINotEnabledException("Set up an AI provider in your group settings to chat with the assistant.")

        history = [OpenAIChatMessage(role=message.role.value, content=message.content) for message in messages]
        text = await self.ai.chat(self.instructions(), history[-MAX_HISTORY:], self.tools())
        if not text and not self.actions:
            raise OpenAIServiceError("The assistant didn't reply. Try asking again.")
        return AssistantChatResponse(reply=text or "Done.", actions=self.actions)

    def instructions(self) -> str:
        today = household_today()
        household = self.repos.households.get_one(self.repos.household_id) if self.repos.household_id else None
        stores = ", ".join(f"{name} ({store.value})" for store, name in STORE_NAMES.items())
        return self.ai.get_prompt(
            "household.assistant",
            data_injections=[
                OpenAIDataInjection(
                    description="Today",
                    value=f"{today:%A}, {today:%B} {today.day}, {today.year} ({today.isoformat()}). "
                    f"This week started on Monday, {monday(today).isoformat()}.",
                ),
                OpenAIDataInjection(
                    description="Who you're talking with",
                    value=f"{self.user_name or 'A household member'}"
                    + (f", in the {household.name} household" if household else ""),
                ),
                OpenAIDataInjection(description="Stores the household shops at", value=stores),
            ],
        )

    def tools(self) -> list[OpenAITool]:
        return [
            self._tool(
                "get_out_of_list",
                "Read the Out of list: what the household has run out of and still needs, with ids, plus what "
                "was bought in the last two weeks.",
                _Args,
                self.get_out_of_list,
            ),
            self._tool(
                "add_out_of_items",
                "Add things the household is out of, or needs to buy, to the Out of list. Something already "
                "on the list is updated rather than added twice.",
                AddOutOfItemsArgs,
                self.add_out_of_items,
            ),
            self._tool(
                "update_out_of_item",
                "Change an Out of item. Send all of its details: they replace the current ones.",
                UpdateOutOfItemArgs,
                self.update_out_of_item,
            ),
            self._tool(
                "remove_out_of_items",
                "Take items off the Out of list, and off the grocery list too unless they were bought.",
                OutOfItemIdsArgs,
                self.remove_out_of_items,
            ),
            self._tool(
                "mark_out_of_items_bought",
                "Mark Out of items bought (or, with bought false, not bought after all). This checks them off "
                "the grocery list too.",
                MarkBoughtArgs,
                self.mark_out_of_items_bought,
            ),
            self._tool(
                "get_grocery_list",
                "Read a week's grocery list: each thing to buy, the store and product picked for it, how much "
                "is needed, and whether it's been bought.",
                GroceryListArgs,
                self.get_grocery_list,
            ),
            self._tool(
                "get_meal_plan",
                "Read the household's meal plan for a range of days, at most 31.",
                MealPlanArgs,
                self.get_meal_plan,
            ),
            self._tool(
                "search_recipes",
                "Find the household's saved recipes by name, description or ingredient.",
                SearchRecipesArgs,
                self.search_recipes,
            ),
            self._tool(
                "get_recipe",
                "Read one saved recipe: its ingredients, steps and notes.",
                RecipeArgs,
                self.get_recipe,
            ),
            self._tool(
                "suggest_dinners",
                "Dinner ideas for a night, from saved recipes that haven't been planned lately, rated well, "
                "or use ingredients on hand.",
                SuggestDinnersArgs,
                self.suggest_dinners,
            ),
            self._tool(
                "plan_meal",
                'Put a meal on the meal plan: a saved recipe, or a title like "Leftovers".',
                PlanMealArgs,
                self.plan_meal,
            ),
        ]

    def _tool(self, name: str, description: str, args: type[BaseModel], handler: Callable[[Any], Any]) -> OpenAITool:
        async def run(arguments: Any) -> str:
            try:
                parsed = args.model_validate(arguments or {})
            except ValidationError as e:
                raise OpenAIToolError(f"Those arguments don't fit: {validation_message(e)}") from e
            try:
                result = handler(parsed)
            except HTTPException as e:
                raise OpenAIToolError(http_message(e)) from e
            except ValidationError as e:
                raise OpenAIToolError(validation_message(e)) from e
            finally:
                # Services commit their own changes; this ends whatever read was left open while the
                # model thinks, which can take a while
                self.repos.session.rollback()
            return json.dumps(result, default=str, ensure_ascii=False)

        return OpenAITool(name=name, description=description, parameters=tool_parameters(args), run=run)

    # ------------------------------------------------------------------
    # The Out of list

    def _restock_json(self, item: GroceryRestockOut) -> dict[str, Any]:
        result: dict[str, Any] = {"id": str(item.id), "name": item.name, "status": item.status.value}
        if text := amount(item.quantity, item.unit):
            result["amount"] = text
        if item.store:
            result["store"] = STORE_NAMES[item.store]
        if item.note:
            result["note"] = item.note
        if item.status == GroceryRestockStatus.listed and item.week_start:
            result["on_list_for_week_of"] = item.week_start.isoformat()
        if item.bought_at:
            result["bought_on"] = item.bought_at.date().isoformat()
        if item.added_by:
            result["added_by"] = item.added_by
        return result

    def _restock_data(self, args: OutOfItemArgs) -> GroceryRestockCreate:
        return GroceryRestockCreate(
            name=args.name,
            quantity=args.quantity,
            unit=args.unit if args.quantity else None,
            store=args.store,
            note=args.note or "",
        )

    def _restock_item(self, item_id: str) -> GroceryRestockItem:
        try:
            return self.repos.grocery_restock_items.item_model(UUID(item_id))
        except ValueError as e:
            raise OpenAIToolError(f"{item_id} isn't an item id. Get ids from get_out_of_list.") from e

    def get_out_of_list(self, _: _Args) -> dict[str, Any]:
        result = self.groceries.restock_list()
        return {
            "next_list_week_of": result.next_list_week.isoformat() if result.next_list_week else None,
            "items": [self._restock_json(item) for item in result.items],
            "recently_bought": [self._restock_json(item) for item in result.recently_bought],
        }

    def add_out_of_items(self, args: AddOutOfItemsArgs) -> dict[str, Any]:
        added = []
        for entry in args.items:
            item, created = self.groceries.add_restock(self._restock_data(entry), added_by=self.user_name)
            self.actions.append(
                AssistantAction(
                    kind="restock",
                    summary=f"Added {item.name} to Out of" if created else f"Updated {item.name} on Out of",
                )
            )
            added.append({**self._restock_json(item), "already_listed": not created})
        result = self.groceries.restock_list()
        return {
            "items": added,
            "next_list_week_of": result.next_list_week.isoformat() if result.next_list_week else None,
        }

    def update_out_of_item(self, args: UpdateOutOfItemArgs) -> dict[str, Any]:
        item = self.groceries.update_restock(self._restock_item(args.id).id, self._restock_data(args))
        self.actions.append(AssistantAction(kind="restock", summary=f"Updated {item.name} on Out of"))
        return {"item": self._restock_json(item)}

    def remove_out_of_items(self, args: OutOfItemIdsArgs) -> dict[str, Any]:
        removed = []
        for item_id in dict.fromkeys(args.ids):
            item = self.groceries.remove_restock(self._restock_item(item_id).id)
            self.actions.append(AssistantAction(kind="restock", summary=f"Removed {item.name} from Out of"))
            removed.append(item.name)
        return {"removed": removed}

    def mark_out_of_items_bought(self, args: MarkBoughtArgs) -> dict[str, Any]:
        changed = []
        for item_id in dict.fromkeys(args.ids):
            item = self.groceries.set_restock_bought(self._restock_item(item_id).id, args.bought)
            summary = f"Marked {item.name} bought" if args.bought else f"Put {item.name} back on the list"
            self.actions.append(AssistantAction(kind="restock", summary=summary))
            changed.append(self._restock_json(item))
        return {"items": changed}

    # ------------------------------------------------------------------
    # Groceries, meal plans and recipes

    def get_grocery_list(self, args: GroceryListArgs) -> dict[str, Any]:
        if args.week_of:
            week_start = monday(args.week_of)
        else:
            newest = self.groceries.weeks.newest_from(monday(household_today()))
            week_start = newest.week_start if newest else monday(household_today())
        view = self.groceries.view(week_start)
        if view.week is None:
            return {"week_of": week_start.isoformat(), "list_made": False}

        items = []
        for purchase in view.purchases:
            entry: dict[str, Any] = {
                "name": purchase.food_name,
                "store": STORE_NAMES[purchase.store] if purchase.store else "not assigned",
                "needs": " + ".join(item.display for item in purchase.items if item.display),
                "bought": all(item.checked for item in purchase.items),
            }
            if purchase.product:
                entry["product"] = purchase.product.name
            if purchase.package_count is not None:
                entry["packages"] = purchase.package_count
            if any((item.extras or {}).get(SOURCE) == "restock" for item in purchase.items):
                entry["from_out_of_list"] = True
            items.append(entry)
        return {
            "week_of": week_start.isoformat(),
            "list_made": True,
            "stores": [STORE_NAMES[store] for store in view.week.stores],
            "left_to_buy": sum(1 for item in items if not item["bought"]),
            "items": items,
        }

    def get_meal_plan(self, args: MealPlanArgs) -> dict[str, Any]:
        start = args.start or household_today()
        end = args.end or start + dt.timedelta(days=6)
        if end < start:
            raise OpenAIToolError("The end has to be on or after the start.")
        end = min(end, start + dt.timedelta(days=30))
        meals = self.repos.meals.page_all(
            PaginationQuery(
                per_page=-1,
                order_by="date",
                order_direction=OrderDirection.asc,
                query_filter=f'date >= "{start}" AND date <= "{end}"',
            )
        ).items
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "meals": [
                {
                    "id": meal.id,
                    "day": short_day(meal.date),
                    "date": meal.date.isoformat(),
                    "meal": meal.entry_type.value,
                    "recipe": meal.recipe.name if meal.recipe else None,
                    "recipe_slug": meal.recipe.slug if meal.recipe else None,
                    "title": meal.title or None,
                    "note": meal.text or None,
                }
                for meal in meals
            ],
        }

    def _recipes(self):
        group_repos = get_repositories(self.repos.session, group_id=self.repos.group_id, household_id=None)
        return group_repos.recipes.by_user(self.user.id)

    def _recipe(self, value: str) -> Recipe:
        recipes = self._recipes()
        recipe = recipes.get_one(value.strip(), key="slug")
        if recipe is None:
            try:
                recipe = recipes.get_one(UUID(value.strip()), key="id")
            except ValueError:
                recipe = None
        if recipe is None:
            raise OpenAIToolError(f"There's no saved recipe {value}. Use search_recipes to find one.")
        return recipe

    def search_recipes(self, args: SearchRecipesArgs) -> dict[str, Any]:
        found = self._recipes().page_all(PaginationQuery(per_page=args.limit), search=args.query).items
        return {
            "recipes": [
                {
                    "id": str(recipe.id),
                    "slug": recipe.slug,
                    "name": recipe.name,
                    "description": (recipe.description or "")[:200] or None,
                    "rating": recipe.rating,
                    "total_time": recipe.total_time,
                }
                for recipe in found
            ]
        }

    def get_recipe(self, args: RecipeArgs) -> dict[str, Any]:
        recipe = self._recipe(args.recipe)
        steps: list[str] = []
        budget = MAX_RECIPE_TEXT
        for step in recipe.recipe_instructions or []:
            text = " ".join(filter(None, [step.title, step.text])).strip()
            if budget <= 0:
                steps.append("(more steps left out)")
                break
            steps.append(text[:budget])
            budget -= len(text)
        return {
            "id": str(recipe.id),
            "slug": recipe.slug,
            "name": recipe.name,
            "description": recipe.description or None,
            "servings": recipe.recipe_servings or None,
            "yield": amount(recipe.recipe_yield_quantity, recipe.recipe_yield) or recipe.recipe_yield or None,
            "total_time": recipe.total_time,
            "rating": recipe.rating,
            "ingredients": [
                " ".join(filter(None, [ingredient.title and f"[{ingredient.title}]", ingredient.display])).strip()
                for ingredient in recipe.recipe_ingredient
            ],
            "steps": steps,
            "notes": [f"{note.title}: {note.text}" if note.title else note.text for note in recipe.notes or []],
        }

    def suggest_dinners(self, args: SuggestDinnersArgs) -> dict[str, Any]:
        return {
            "day": short_day(args.day),
            "ideas": [
                {
                    "recipe": suggestion.recipe.name,
                    "slug": suggestion.recipe.slug,
                    "id": str(suggestion.recipe.id),
                    "why": suggestion.reasons,
                }
                for suggestion in self.groceries.suggestions(args.day, limit=5)
            ],
        }

    def plan_meal(self, args: PlanMealArgs) -> dict[str, Any]:
        recipe = self._recipe(args.recipe) if args.recipe else None
        title = (args.title or "").strip()
        if recipe is None and not title:
            raise OpenAIToolError("Give a saved recipe or a title to plan.")
        entry = self.repos.meals.create(
            SavePlanEntry(
                date=args.day,
                entry_type=args.meal,
                recipe_id=recipe.id if recipe else None,
                title="" if recipe else title,
                text=(args.note or "").strip(),
                group_id=self.repos.group_id,
                user_id=self.user.id,
            )
        )
        name = recipe.name if recipe else title
        self.actions.append(
            AssistantAction(kind="mealplan", summary=f"Planned {name} for {args.meal.value} on {short_day(args.day)}")
        )
        return {"planned": {"id": entry.id, "day": short_day(args.day), "meal": args.meal.value, "what": name}}
