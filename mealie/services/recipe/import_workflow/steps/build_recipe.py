from mealie.schema.group.ai_providers import AITask
from mealie.schema.openai.recipe import OpenAIRecipe
from mealie.services.openai import transcription
from mealie.services.scraper import cleaner

from ..base import WorkflowStep
from ..context import WorkflowContext
from ..exceptions import NoRecipeDataError
from ..recipe_conversion import to_recipe

BUILD_RECIPE_PROMPT = "recipes.build-recipe"


class BuildRecipeStep(WorkflowStep):
    """Turns the Compiled Source Document into a draft recipe."""

    name = "build-recipe"
    progress_key = "recipe.create-progress.creating-recipe"

    def _build_message(self, ctx: WorkflowContext) -> str:
        compiled = ctx.compiled_source
        if not compiled:
            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.unreadable-source"))

        return f"Below is the transcribed recipe source.\n\n{compiled.content}"

    async def run(self, ctx: WorkflowContext) -> None:
        response = await ctx.ai.get_response(
            ctx.ai.get_prompt(BUILD_RECIPE_PROMPT),
            self._build_message(ctx),
            response_schema=OpenAIRecipe,
            task=AITask.recipe_building,
        )

        if not response:
            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.provider-returned-nothing"))

        if not (response.ingredients or response.instructions):
            url = ctx.resolved_url or ctx.input.url or ""
            # A post that's only a teaser ("full recipe at the link in our bio") is common enough on
            # the video sites to say so, and what to do instead
            if transcription.is_video_site(url):
                raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.post-has-no-recipe"))
            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.no-recipe-found"))

        ctx.draft_recipe = cleaner.clean(to_recipe(ctx, response), ctx.translator)
