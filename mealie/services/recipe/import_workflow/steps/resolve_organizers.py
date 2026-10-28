from ...recipe_classifier import RecipeClassifier
from ..base import WorkflowStep
from ..context import WorkflowContext


class ResolveOrganizersStep(WorkflowStep):
    """Classify a draft using the same policy as URL and bulk imports."""

    name = "resolve-organizers"
    progress_key = "recipe.create-progress.organizing-recipe"
    required = False

    def should_run(self, ctx: WorkflowContext) -> bool:
        return ctx.options.resolve_organizers

    async def run(self, ctx: WorkflowContext) -> None:
        if not ctx.draft_recipe:
            return
        classifier = RecipeClassifier(ctx.repos, ctx.ai)
        names = await classifier.suggest(
            ctx.draft_recipe,
            source=ctx.compiled_source.content if ctx.compiled_source else "",
            create_new=ctx.options.create_new_organizers,
        )
        ctx.organizer_names = names
        if ctx.options.attach_organizers:
            classifier.attach(ctx.draft_recipe, names, create_new=ctx.options.create_new_organizers)
