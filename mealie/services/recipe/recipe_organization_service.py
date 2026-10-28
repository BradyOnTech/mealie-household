from mealie.core.exceptions import PermissionDenied
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_organization import RecipeOrganizationIn, RecipeOrganizationOut
from mealie.services.openai.openai import OpenAINotEnabledException

from .recipe_classifier import RecipeClassifier
from .recipe_service import RecipeService


class RecipeOrganizationService(RecipeService):
    """Review classification before making additive changes to existing recipes."""

    def _editable_recipes(self, keys: list[str]) -> list[Recipe]:
        recipes = [self.get_one(key) for key in keys]
        if not self.can_update([recipe.slug for recipe in recipes]):
            raise PermissionDenied("You do not have permission to edit these recipes")
        return recipes

    async def preview(self, slugs: list[str]) -> list[RecipeOrganizationOut]:
        recipes = self._editable_recipes(list(dict.fromkeys(slugs)))
        classifier = RecipeClassifier(self.repos)
        if not classifier.enabled:
            raise OpenAINotEnabledException()

        results: list[RecipeOrganizationOut] = []
        for recipe in recipes:
            names = OpenAIOrganizers()
            failed = False
            try:
                names = await classifier.suggest(recipe)
            except Exception:
                self.logger.exception("Failed to preview recipe organization")
                failed = True
            results.append(
                RecipeOrganizationOut(
                    recipe_id=recipe.id,
                    name=recipe.name or recipe.slug,
                    slug=recipe.slug,
                    error=failed,
                    **names.model_dump(),
                )
            )
        return results

    def apply(self, suggestions: list[RecipeOrganizationIn]) -> None:
        # Preflight the whole batch before creating any labels. Re-read current recipes so edits
        # made since preview aren't overwritten, and permissions are checked again at apply time.
        recipes = self._editable_recipes([str(s.recipe_id) for s in suggestions])
        classifier = RecipeClassifier(self.repos)
        for recipe, suggestion in zip(recipes, suggestions, strict=True):
            names = OpenAIOrganizers(**suggestion.model_dump(exclude={"recipe_id"}))
            classifier.attach(recipe, names)
            self.update_one(recipe.slug, recipe)
