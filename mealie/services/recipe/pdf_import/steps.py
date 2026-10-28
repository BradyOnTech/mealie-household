from collections.abc import Sequence
from pathlib import Path

from mealie.schema.group.ai_providers import AITask
from mealie.schema.openai.compiled_source import OpenAICompiledSource
from mealie.schema.openai.recipe import OpenAIRecipe
from mealie.services.openai import OpenAILocalImage
from mealie.services.scraper import cleaner

from ..import_workflow import WorkflowContext, WorkflowStep
from ..import_workflow.exceptions import NoRecipeDataError
from ..import_workflow.recipe_conversion import to_recipe
from .pdf_document import PdfPage

BUILD_RECIPE_PROMPT = "recipes.build-recipe"
BUILD_RECIPE_FROM_PDF_PROMPT = "recipes.build-recipe-from-pdf"

NO_TEXT_PLACEHOLDER = "[No text could be extracted from this page]"


def format_pages(pages: Sequence[PdfPage]) -> str:
    """Lays out pages for the AI, each under a marker with its page number."""

    return "\n\n".join(f"--- Page {page.number} ---\n{page.text or NO_TEXT_PLACEHOLDER}" for page in pages)


class BuildRecipeFromPdfStep(WorkflowStep):
    """
    Reads one recipe from the pages of a PDF into a draft recipe.

    This takes the place of both the compile and build steps. A PDF's text needs no transcribing,
    but it often needs the page images alongside it, since designed cookbooks scatter their text
    out of reading order.
    """

    name = "build-recipe-from-pdf"
    progress_key = "recipe.create-progress.creating-recipe"

    def __init__(self, recipe_name: str, pages: Sequence[PdfPage], page_images: Sequence[Path] = ()) -> None:
        self.recipe_name = recipe_name
        self.pages = list(pages)
        self.page_images = list(page_images)

    async def run(self, ctx: WorkflowContext) -> None:
        content = format_pages(self.pages)
        # later steps, like resolving organizers, read the source from here
        ctx.compiled_source = OpenAICompiledSource(contains_recipe=True, content=content, language=None, image_url=None)

        prompt = "\n\n".join([ctx.ai.get_prompt(BUILD_RECIPE_PROMPT), ctx.ai.get_prompt(BUILD_RECIPE_FROM_PDF_PROMPT)])
        attachments = [OpenAILocalImage(filename=image.name, path=image) for image in self.page_images]
        response = await ctx.ai.get_response(
            prompt,
            f"Recipe: {self.recipe_name}\n\n{content}",
            response_schema=OpenAIRecipe,
            attachments=attachments or None,
            task=AITask.cookbook_extraction,
        )

        if not response:
            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.provider-returned-nothing"))

        if not (response.ingredients or response.instructions):
            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.no-recipe-found"))

        ctx.draft_recipe = cleaner.clean(to_recipe(ctx, response), ctx.translator)
