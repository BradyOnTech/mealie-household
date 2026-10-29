from dataclasses import dataclass

from mealie.core import exceptions
from mealie.core.root_logger import get_logger
from mealie.pkgs.safehttp import resilient_fetch
from mealie.schema.openai.compiled_source import OpenAICompiledSource
from mealie.services.openai import transcription
from mealie.services.openai.content import has_recipe_data, truncate_source_parts

from ..base import WorkflowStep
from ..compilers import DEFAULT_SOURCE_COMPILERS, SourceCompiler, SourceType
from ..context import WorkflowContext
from ..exceptions import NoRecipeDataError

IMAGES_LABEL = "Uploaded images"
PAGE_LABEL = "Recipe source page"
CONTENT_LABEL = "Content supplied by the user"

MULTI_SOURCE_PREAMBLE = (
    "The source material is split into the sections below. They all describe the same recipe, so "
    "treat them as a single source; where they disagree, prefer the content supplied by the user."
)


@dataclass
class CompiledDocument:
    """One compiled source, labelled with where it came from."""

    label: str
    compiled: OpenAICompiledSource

    @property
    def is_usable(self) -> bool:
        return self.compiled.contains_recipe and bool(self.compiled.content.strip())


class CompileSourceStep(WorkflowStep):
    """
    Compiles the workflow input into a Compiled Source Document: a faithful transcription of
    the source material that later steps read instead of the raw input.

    Every source the input carries is compiled and the results are merged into one document, so
    content pasted alongside a URL adds to what the page says rather than replacing it. Combining
    sources is this step's job alone; a compiler only ever sees the one source it was given.
    """

    name = "compile-source"

    def __init__(self, compilers: list[type[SourceCompiler]] | None = None) -> None:
        self.compilers = DEFAULT_SOURCE_COMPILERS if compilers is None else compilers
        self.logger = get_logger()

    async def _compile(
        self, ctx: WorkflowContext, source_type: SourceType, content: str | None = None, *, final: bool = False
    ) -> OpenAICompiledSource | None:
        """
        Compiles a source with the first compiler that can. A compiler that fails hands the source
        on to the next one, unless the result is `final`: then there's nowhere better to read the
        source from, and its error says more about what went wrong than any fallback's would.
        """

        for CompilerClass in self.compilers:
            if CompilerClass.source_type is not source_type:
                continue

            compiler = CompilerClass(ctx, content)
            if not compiler.can_compile():
                continue

            if compiler.progress_key:
                await ctx.report_progress(compiler.progress_key)

            try:
                compiled = await compiler.compile()
            except exceptions.RateLimitError:
                # every other compiler would run into the same limit
                raise
            except Exception:
                if final:
                    raise

                # `can_compile` judges the shape of the source, not whether it can actually be read.
                # yt-dlp recognises every cooking.nytimes.com/recipes/<id> URL, for instance, but
                # most of those pages carry no video at all. Hand the source to the next compiler —
                # and, for a URL, on to fetching the page as HTML — rather than failing the import.
                self.logger.exception("Failed to compile source with %s", CompilerClass.__name__)
                continue

            if compiled:
                return compiled

        return None

    async def _compile_images(self, ctx: WorkflowContext) -> OpenAICompiledSource | None:
        if not ctx.input.images:
            return None

        return await self._compile(ctx, SourceType.IMAGES)

    async def _compile_content(self, ctx: WorkflowContext, content: str | None) -> OpenAICompiledSource | None:
        if not content:
            return None

        return await self._compile(ctx, SourceType.CONTENT, content)

    async def _compile_page(self, ctx: WorkflowContext) -> OpenAICompiledSource | None:
        url = ctx.input.url
        if not url:
            return await self._compile_content(ctx, ctx.input.page_content)

        # Video compilers read these posts directly, including written captions that may need their
        # own page fetch. Avoid running the generic webpage compiler over the surrounding site.
        read_urls: set[str] = set()
        if transcription.is_video_site(url):
            read_urls.add(url)
            if compiled := await self._compile(ctx, SourceType.URL, final=True):
                return compiled

        page_content = ctx.input.page_content
        if not page_content:
            await ctx.report_progress("recipe.create-progress.fetching-webpage")
            result = await resilient_fetch(url)
            if result:
                page_content = result.text
                ctx.resolved_url = result.url

        # Anywhere else, a page that publishes its recipe as structured data is the best source
        # there is. yt-dlp knows a few recipe sites (NYT Cooking and BBC Food among them), but their
        # videos only demonstrate the written recipe. Share links, meanwhile, aren't recognized as
        # videos until after their redirect, so they're read with the landing URL.
        landing_url = ctx.resolved_url or url
        if (
            landing_url not in read_urls
            and self._can_compile_url(ctx)
            and not (page_content and has_recipe_data(page_content))
        ):
            final = transcription.is_video_site(landing_url)
            if compiled := await self._compile(ctx, SourceType.URL, final=final):
                return compiled

        return await self._compile_content(ctx, page_content)

    def _can_compile_url(self, ctx: WorkflowContext) -> bool:
        return any(
            CompilerClass.source_type is SourceType.URL and CompilerClass(ctx).can_compile()
            for CompilerClass in self.compilers
        )

    def _merge(self, ctx: WorkflowContext, documents: list[CompiledDocument]) -> OpenAICompiledSource:
        usable = [document for document in documents if document.is_usable]
        if not usable:
            # a source that compiled but produced nothing was readable, it just had no recipe in it
            if documents:
                raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.no-recipe-found"))

            raise NoRecipeDataError(ctx.translator.t("recipe.import-errors.unreadable-source"))

        contents = truncate_source_parts([document.compiled.content for document in usable])
        if len(usable) > 1:
            contents = [f"## {document.label}\n\n{text}" for document, text in zip(usable, contents, strict=True)]
            contents.insert(0, MULTI_SOURCE_PREAMBLE)

        return OpenAICompiledSource(
            contains_recipe=True,
            content="\n\n".join(contents),
            language=next((document.compiled.language for document in usable if document.compiled.language), None),
            image_url=next((document.compiled.image_url for document in usable if document.compiled.image_url), None),
        )

    async def run(self, ctx: WorkflowContext) -> None:
        # the user's own content goes last, so it reads as an addendum to what it accompanies
        sources = [
            (IMAGES_LABEL, await self._compile_images(ctx)),
            (PAGE_LABEL, await self._compile_page(ctx)),
            (CONTENT_LABEL, await self._compile_content(ctx, ctx.input.content)),
        ]

        ctx.compiled_source = self._merge(
            ctx, [CompiledDocument(label, compiled) for label, compiled in sources if compiled]
        )
