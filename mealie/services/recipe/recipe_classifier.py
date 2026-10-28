from slugify import slugify

from mealie.repos.repository_factory import AllRepositories
from mealie.schema.group.ai_providers import AITask
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.recipe.recipe import Recipe, RecipeTag
from mealie.services.matching import find_match
from mealie.services.openai import OpenAIDataInjection, OpenAIService
from mealie.services.openai.content import truncate_source_content

from .organizer_resolver import ORGANIZER_FUZZY_MATCH_THRESHOLD, OrganizerResolver

# Only these names may be created automatically. Existing group vocabulary takes precedence.
STANDARD_ORGANIZERS = {
    "categories": ("Breakfast", "Main Dish", "Side Dish", "Appetizer", "Dessert", "Snack", "Drink", "Sauce"),
    "tags": (
        "Chicken",
        "Beef",
        "Pork",
        "Lamb",
        "Turkey",
        "Fish",
        "Seafood",
        "Tofu",
        "Beans",
        "Lentils",
        "Eggs",
        "Pasta",
        "Rice",
        "Soup",
        "Salad",
        "Bread",
        "Casserole",
        "Sandwich",
        "Pizza",
        "One Pot",
        "Traybake",
        "Slow Cooked",
        "Pressure Cooked",
        "Grilled",
        "Baked",
        "No Cook",
        "Quick",
        "Freezer Friendly",
        "Make Ahead",
    ),
    "tools": (
        "Oven",
        "Sheet Pan",
        "Skillet",
        "Saucepan",
        "Stockpot",
        "Dutch Oven",
        "Slow Cooker",
        "Pressure Cooker",
        "Grill",
        "Blender",
        "Food Processor",
        "Stand Mixer",
        "Air Fryer",
    ),
}


class RecipeClassifier:
    """Suggest labels without writes, then add accepted labels without replacing existing ones."""

    def __init__(self, repos: AllRepositories, ai: OpenAIService | None = None) -> None:
        self.repos = repos
        self.ai = ai if ai is not None else OpenAIService(repos)

    @property
    def enabled(self) -> bool:
        settings = self.ai.provider_settings
        return bool(settings and settings.ai_enabled and self.ai.route(AITask.organizer_matching))

    @staticmethod
    def _message(recipe: Recipe, source: str) -> str:
        # Cookbook pages can contain neighboring recipes, so identify the target first.
        parts = [f"Recipe to classify:\n{recipe.name or ''}", recipe.description or ""]
        parts.append("Ingredients:\n" + "\n".join(i.display or i.note or "" for i in recipe.recipe_ingredient))
        parts.append("Instructions:\n" + "\n".join(i.text for i in recipe.recipe_instructions or []))
        parts.append(f"Total time: {recipe.total_time or 'Unknown'}")
        parts.append("Recipe notes:\n" + "\n".join(n.text for n in recipe.notes or []))
        if source:
            parts.append("Source context (use only statements about this recipe):\n" + source)
        return truncate_source_content("\n\n".join(parts))

    def normalize(self, names: OpenAIOrganizers, *, create_new: bool = False) -> OpenAIOrganizers:
        """Enforce the vocabulary on model output and accepted preview payloads alike."""
        resolver = OrganizerResolver(self.repos)
        stores = {"tags": resolver.tags, "categories": resolver.categories, "tools": resolver.tools}
        normalized: dict[str, list[str]] = {}
        for kind, store in stores.items():
            standard = {slugify(name): name for name in STANDARD_ORGANIZERS[kind]}
            result: dict[str, str] = {}
            for name in getattr(names, kind):
                key = slugify(name)
                if not key:
                    continue
                match = find_match(key, store_map=store, fuzzy_match_threshold=ORGANIZER_FUZZY_MATCH_THRESHOLD)
                canonical = match.name if match else standard.get(key)
                if canonical is None and create_new:
                    canonical = name.strip()[:100]
                if canonical:
                    result.setdefault(slugify(canonical), canonical)
            normalized[kind] = list(result.values())[: (3 if kind == "categories" else 8)]
        return OpenAIOrganizers(**normalized)

    async def suggest(self, recipe: Recipe, *, source: str = "", create_new: bool = False) -> OpenAIOrganizers:
        if not self.enabled:
            return OpenAIOrganizers()
        existing = OrganizerResolver(self.repos).existing_names()
        injections = [
            OpenAIDataInjection(
                description="Existing group labels. Prefer these exact names over synonyms or standard labels.",
                value=existing,
            ),
            OpenAIDataInjection(
                description="Standard labels available when no existing label fits. Choose only relevant labels.",
                value=STANDARD_ORGANIZERS,
            ),
            OpenAIDataInjection(
                description="Whether additional names outside the existing and standard labels are allowed.",
                value="yes" if create_new else "no",
            ),
        ]
        response = await self.ai.get_response(
            self.ai.get_prompt("recipes.resolve-organizers", data_injections=injections),
            self._message(recipe, source),
            response_schema=OpenAIOrganizers,
            task=AITask.organizer_matching,
        )
        if response is None:
            raise ValueError("Recipe classification returned no response")
        return self.normalize(response, create_new=create_new)

    @staticmethod
    def _merge[T: RecipeTag](existing: list[T] | None, additions: list[T]) -> list[T]:
        merged = {item.id: item for item in existing or []}
        for item in additions:
            merged.setdefault(item.id, item)
        return list(merged.values())

    def attach(self, recipe: Recipe, names: OpenAIOrganizers, *, create_new: bool = False) -> None:
        names = self.normalize(names, create_new=create_new)
        resolver = OrganizerResolver(self.repos)
        recipe.tags = self._merge(recipe.tags, resolver.resolve_tags(names.tags, create_missing=True))
        recipe.recipe_category = self._merge(
            recipe.recipe_category, resolver.resolve_categories(names.categories, create_missing=True)
        )
        recipe.tools = self._merge(recipe.tools, resolver.resolve_tools(names.tools, create_missing=True))
