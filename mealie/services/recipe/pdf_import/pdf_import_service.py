"""
Imports every recipe in a PDF cookbook.

The import runs in two passes:

1. Find the recipes. The pages' text goes to the AI in overlapping chunks, and it lists each recipe
   with the pages it's on.
2. Import them, one AI request per recipe, with the text and an image of each of its pages. The
   recipe's photo is cut out of the PDF rather than left to the AI.

A whole cookbook takes a lot of AI requests, and a ChatGPT subscription provider can hit its plan's
usage limit partway through. So each recipe records the PDF and page it came from in an API extra,
and importing the same PDF again skips the recipes that made it in last time.
"""

import asyncio
import hashlib
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from pydantic import UUID4
from slugify import slugify

from mealie.core import exceptions
from mealie.core.config import get_app_dirs
from mealie.core.dependencies.dependencies import get_temporary_path
from mealie.db.db_setup import session_context
from mealie.lang.providers import Translator, get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.cookbook.cookbook import SaveCookBook
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.openai.pdf_recipes import OpenAIPdfRecipeLocations
from mealie.schema.recipe.recipe import Recipe, RecipeTag
from mealie.schema.recipe.recipe_notes import RecipeNote
from mealie.schema.reports.reports import ReportCategory, ReportCreate, ReportEntryCreate, ReportSummaryStatus
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.user.user import PrivateUser
from mealie.services.openai import OpenAILocalImage, OpenAINotEnabledException, OpenAIService
from mealie.services.scraper.scraper import finalize_scraped_recipe

from ..import_workflow import RecipeImportWorkflow, WorkflowContext, WorkflowInput, WorkflowOptions, WorkflowStep
from ..import_workflow.exceptions import NoRecipeDataError
from ..import_workflow.steps import ResolveOrganizersStep
from ..organizer_resolver import OrganizerResolver
from ..recipe_data_service import RecipeDataService
from ..recipe_service import RecipeService
from .pdf_document import PdfPage, PdfReadError, count_pages, extract_photo, read_pages, render_page, run_pdfium
from .steps import BuildRecipeFromPdfStep, format_pages

FIND_RECIPES_PROMPT = "recipes.find-pdf-recipes"

PDF_SOURCE_EXTRA = "pdf_source"
"""API extra recording the PDF and page a recipe was imported from, as `<sha256>#page=<number>`"""

INDEX_MAX_PAGES = 24
INDEX_MAX_CHARS = 40_000
INDEX_MAX_IMAGES = 8

INDEX_OVERLAP_PAGES = 3
"""
How many pages each chunk repeats from the end of the one before. A recipe that starts near the end
of a chunk is cut off there, so the next chunk, which sees it whole, is the one that lists it.
"""

MAX_RECIPE_PAGES = 6
MAX_CONSECUTIVE_FAILURES = 5

RETRY_DELAY_SECONDS = 30
"""How long to wait before trying failed recipes again, to give a passing problem time to clear"""

DEFAULT_COOKBOOK_NAME = "Cookbook"

_running_imports: set[tuple[UUID4, str]] = set()
"""Group and PDF fingerprint of every import in progress, so the same PDF isn't imported twice at once"""


class PdfImportError(Exception):
    """The import couldn't be started. The message is meant for the user."""


class PdfImportInProgressError(PdfImportError):
    """The same PDF is already being imported."""


class ImportStoppedError(Exception):
    """Ends an import early. The message is meant for the report."""


@dataclass(frozen=True)
class PdfRecipeLocation:
    name: str
    first_page: int
    last_page: int

    @property
    def page_numbers(self) -> range:
        return range(self.first_page, self.last_page + 1)


@dataclass
class _ImportTally:
    imported: int = 0
    failed: int = 0
    stopped: bool = False


@dataclass
class PdfImportJob:
    """An import that's been accepted, to be run in the background."""

    report_id: UUID4
    pdf_path: Path
    fingerprint: str
    cookbook_name: str
    add_cookbook: bool
    add_organizers: bool

    user: PrivateUser
    household: HouseholdInDB
    translator: Translator

    async def run(self) -> None:
        """Runs the import with its own database session, since it outlives the request that started it."""

        try:
            with session_context() as session:
                repos = get_repositories(session, group_id=self.user.group_id, household_id=self.household.id)
                service = PdfRecipeImportService(repos, self.user, self.household, self.translator)
                await service.run(self)
        finally:
            shutil.rmtree(self.pdf_path.parent, ignore_errors=True)
            _running_imports.discard((self.user.group_id, self.fingerprint))


def close_interrupted_imports() -> None:
    """
    Closes the reports of imports that were still running when Mealie last stopped. Imports run in
    the app's own process, so none of them can still be running when it starts up.
    """

    translator = get_locale_provider("en-US")
    with session_context() as session:
        repos = get_repositories(session, group_id=None, household_id=None)
        interrupted = repos.group_reports.multi_query(
            {"category": ReportCategory.pdf_import, "status": ReportSummaryStatus.in_progress}
        )

        for report in interrupted:
            repos.group_report_entries.create(
                ReportEntryCreate(
                    report_id=report.id,
                    success=False,
                    message=translator.t("recipe.pdf-import.interrupted"),
                )
            )
            imported_any = any(entry.success for entry in report.entries)
            report.status = ReportSummaryStatus.partial if imported_any else ReportSummaryStatus.failure
            repos.group_reports.update(report.id, report)


def _save_upload(source: BinaryIO, dest: Path) -> str:
    """Copies an upload to disk, returning the SHA-256 of its contents."""

    digest = hashlib.sha256()
    with dest.open("wb") as f:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            f.write(chunk)
    return digest.hexdigest()


def _cookbook_name(name: str | None, filename: str | None) -> str:
    """The cookbook's name, falling back to the file's name. It names a tag, so it must have a slug."""

    candidates = [(name or "").strip(), Path(filename or "").stem.strip()]
    return next((candidate for candidate in candidates if slugify(candidate)), DEFAULT_COOKBOOK_NAME)


def _chunk_pages(pages: Sequence[PdfPage], *, with_images: bool) -> list[list[PdfPage]]:
    """
    Splits pages into overlapping chunks small enough for one request each. Pages without text count
    against the image limit instead, since they're sent as images.
    """

    chunks: list[list[PdfPage]] = []
    start = 0
    while start < len(pages):
        end, chars, images = start, 0, 0
        while end < len(pages) and end - start < INDEX_MAX_PAGES:
            page = pages[end]
            needs_image = with_images and not page.text
            if end > start and (chars + len(page.text) > INDEX_MAX_CHARS or images + needs_image > INDEX_MAX_IMAGES):
                break

            chars += len(page.text)
            images += needs_image
            end += 1

        chunks.append(list(pages[start:end]))
        if end >= len(pages):
            break
        start = max(end - INDEX_OVERLAP_PAGES, start + 1)

    return chunks


def _settle(locations: list[PdfRecipeLocation]) -> list[PdfRecipeLocation]:
    """Orders recipes by page, dropping duplicates, and ends each before the next one starts."""

    unique: dict[tuple[int, str], PdfRecipeLocation] = {}
    for location in sorted(locations, key=lambda loc: loc.first_page):
        unique.setdefault((location.first_page, slugify(location.name)), location)

    ordered = list(unique.values())
    settled: list[PdfRecipeLocation] = []
    for location in ordered:
        next_start = next((loc.first_page for loc in ordered if loc.first_page > location.first_page), None)
        last_page = location.last_page if next_start is None else min(location.last_page, next_start - 1)
        settled.append(PdfRecipeLocation(location.name, location.first_page, max(last_page, location.first_page)))

    return settled


def _source_prefix(fingerprint: str) -> str:
    return f"{fingerprint}#page="


def _source_value(fingerprint: str, page: int) -> str:
    return f"{_source_prefix(fingerprint)}{page}"


class PdfRecipeImportService(RecipeService):
    """Imports every recipe in a PDF cookbook, recording each in a report as it goes."""

    def __init__(
        self, repos: AllRepositories, user: PrivateUser, household: HouseholdInDB, translator: Translator
    ) -> None:
        super().__init__(repos, user, household, translator)
        self.ai = OpenAIService(repos)

    # =======================================================================
    # Starting an import

    async def prepare(
        self,
        upload: BinaryIO,
        *,
        filename: str | None,
        cookbook_name: str | None,
        add_cookbook: bool,
        add_organizers: bool,
    ) -> PdfImportJob:
        """
        Checks that the upload can be imported and stores it for the background job, creating the report
        the job will fill in. Raises `PdfImportError` if it can't be imported.
        """

        settings = self.ai.provider_settings
        if not (settings and settings.ai_enabled):
            raise PdfImportError(self.t("recipe.import-errors.ai-not-enabled"))

        work_dir = get_app_dirs().TEMP_DIR.joinpath("pdf-imports", uuid4().hex)
        work_dir.mkdir(parents=True)
        pdf_path = work_dir.joinpath("cookbook.pdf")

        try:
            fingerprint = await asyncio.to_thread(_save_upload, upload, pdf_path)
            await run_pdfium(count_pages, pdf_path)
        except PdfReadError as e:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise PdfImportError(self.t("recipe.pdf-import.unreadable")) from e
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        key = (self.user.group_id, fingerprint)
        if key in _running_imports:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise PdfImportInProgressError(self.t("recipe.pdf-import.already-importing"))

        name = _cookbook_name(cookbook_name, filename)
        _running_imports.add(key)
        try:
            report = self.repos.group_reports.create(
                ReportCreate(name=name, category=ReportCategory.pdf_import, group_id=self.user.group_id)
            )
        except Exception:
            _running_imports.discard(key)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        return PdfImportJob(
            report_id=report.id,
            pdf_path=pdf_path,
            fingerprint=fingerprint,
            cookbook_name=name,
            add_cookbook=add_cookbook,
            add_organizers=add_organizers,
            user=self.user,
            household=self.household,
            translator=self.translator,
        )

    # =======================================================================
    # Running an import

    async def run(self, job: PdfImportJob) -> None:
        status = ReportSummaryStatus.failure
        try:
            status = await self._import(job)
        except Exception as e:
            self.logger.exception("PDF import failed")
            self.repos.session.rollback()
            self._add_entry(job, self.t("recipe.pdf-import.unexpected-error"), success=False, exception=str(e))
        finally:
            self._set_status(job, status)

    async def _import(self, job: PdfImportJob) -> ReportSummaryStatus:
        pages = await run_pdfium(read_pages, job.pdf_path)
        with_images = self.ai.image_provider is not None

        try:
            if not (with_images or any(page.text for page in pages)):
                raise ImportStoppedError(self.t("recipe.pdf-import.needs-image-provider"))
            locations = await self._find_recipes(job, pages, with_images=with_images)
        except ImportStoppedError as e:
            self._add_entry(job, str(e), success=False, exception=str(e.__cause__ or ""))
            return ReportSummaryStatus.failure

        if not locations:
            self._add_entry(job, self.t("recipe.pdf-import.no-recipes-found"), success=False)
            return ReportSummaryStatus.failure

        self._add_entry(job, self.t("recipe.pdf-import.found-recipes", count=len(locations), pages=len(pages)))

        imported_pages = self._imported_pages(job.fingerprint)
        remaining = [location for location in locations if location.first_page not in imported_pages]
        if skipped := len(locations) - len(remaining):
            self._add_entry(job, self.t("recipe.pdf-import.skipped-imported", count=skipped))
        if not remaining:
            return ReportSummaryStatus.success

        tag = self._cookbook_tag(job.cookbook_name)
        if job.add_cookbook:
            self._add_cookbook(job.cookbook_name, tag)

        pages_by_number = {page.number: page for page in pages}
        tally = await self._import_all(job, remaining, pages_by_number, tag, with_images=with_images)

        if not (tally.failed or tally.stopped):
            return ReportSummaryStatus.success
        if tally.imported or skipped:
            return ReportSummaryStatus.partial
        return ReportSummaryStatus.failure

    async def _import_all(
        self,
        job: PdfImportJob,
        locations: Sequence[PdfRecipeLocation],
        pages_by_number: dict[int, PdfPage],
        tag: RecipeTag,
        *,
        with_images: bool,
    ) -> _ImportTally:
        """
        Imports each recipe in turn. A request can fail for a passing reason, like a dropped
        connection or a response that stalls, so a recipe that fails that way gets a second try once
        the rest are done.
        """

        tally = _ImportTally()
        retries: list[tuple[PdfRecipeLocation, Exception]] = []

        async def attempt(location: PdfRecipeLocation) -> Exception | None:
            try:
                recipe = await self._import_recipe(job, location, pages_by_number, tag, with_images=with_images)
            except ImportStoppedError:
                raise
            except Exception as e:
                self.logger.exception(f"Failed to import the recipe on page {location.first_page} of a PDF")
                self.repos.session.rollback()
                return e

            tally.imported += 1
            self._add_entry(job, self.t("recipe.pdf-import.imported", name=recipe.name, page=location.first_page))
            return None

        try:
            consecutive_failures = 0
            for location in locations:
                if not (error := await attempt(location)):
                    consecutive_failures = 0
                    continue

                if isinstance(error, NoRecipeDataError):
                    # the AI read the pages and found no recipe, which asking again won't change
                    self._add_failure(job, tally, location, error)
                else:
                    retries.append((location, error))

                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise ImportStoppedError(
                        self.t("recipe.pdf-import.stopped-repeated-failures", count=consecutive_failures)
                    )

            if retries:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            while retries:
                location, _ = retries[0]
                if error := await attempt(location):
                    self._add_failure(job, tally, location, error)
                retries.pop(0)
        except ImportStoppedError as e:
            for location, error in retries:
                self._add_failure(job, tally, location, error)
            self._add_entry(job, str(e), success=False, exception=str(e.__cause__ or ""))
            tally.stopped = True

        return tally

    async def _find_recipes(
        self, job: PdfImportJob, pages: Sequence[PdfPage], *, with_images: bool
    ) -> list[PdfRecipeLocation]:
        chunks = _chunk_pages(pages, with_images=with_images)
        # a page in two chunks belongs to the later one, which sees more of what follows it
        owners = {page.number: i for i, chunk in enumerate(chunks) for page in chunk}
        prompt = self.ai.get_prompt(FIND_RECIPES_PROMPT)

        found: list[PdfRecipeLocation] = []
        for i, chunk in enumerate(chunks):
            first, last = chunk[0].number, chunk[-1].number
            response: OpenAIPdfRecipeLocations | None = None
            for try_number in (1, 2):
                try:
                    response = await self._find_recipes_in(job.pdf_path, chunk, prompt, with_images=with_images)
                    break
                except Exception as e:
                    if reason := self._stop_reason(e):
                        raise ImportStoppedError(reason) from e

                    self.logger.exception(f"Failed to find recipes on pages {first}-{last} of a PDF")
                    if try_number == 1:
                        # it may have been a passing problem, so give it a moment and try again
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        self._add_entry(
                            job,
                            self.t("recipe.pdf-import.unreadable-pages", first=first, last=last),
                            success=False,
                            exception=str(e),
                        )

            for location in response.recipes if response else []:
                name = location.name.strip()
                if not name or owners.get(location.first_page) != i:
                    continue

                last_page = min(max(location.last_page, location.first_page), last)
                last_page = min(last_page, location.first_page + MAX_RECIPE_PAGES - 1)
                found.append(PdfRecipeLocation(name, location.first_page, last_page))

        return _settle(found)

    async def _find_recipes_in(
        self, pdf_path: Path, pages: Sequence[PdfPage], prompt: str, *, with_images: bool
    ) -> OpenAIPdfRecipeLocations | None:
        with get_temporary_path() as temp_path:
            # pages without text can only be read from an image of them
            attachments: list[OpenAILocalImage] = []
            for page in pages:
                if with_images and not page.text:
                    dest = temp_path.joinpath(f"page-{page.number}.jpg")
                    image = await run_pdfium(render_page, pdf_path, page.number, dest)
                    attachments.append(OpenAILocalImage(filename=image.name, path=image))

            return await self.ai.get_response(
                prompt,
                format_pages(pages),
                response_schema=OpenAIPdfRecipeLocations,
                attachments=attachments or None,
            )

    async def _import_recipe(
        self,
        job: PdfImportJob,
        location: PdfRecipeLocation,
        pages_by_number: dict[int, PdfPage],
        tag: RecipeTag,
        *,
        with_images: bool,
    ) -> Recipe:
        pages = [pages_by_number[number] for number in location.page_numbers if number in pages_by_number]

        with get_temporary_path() as temp_path:
            page_images: list[Path] = []
            if with_images:
                for page in pages:
                    dest = temp_path.joinpath(f"page-{page.number}.jpg")
                    page_images.append(await run_pdfium(render_page, job.pdf_path, page.number, dest))

            photo = await run_pdfium(
                extract_photo, job.pdf_path, list(location.page_numbers), temp_path.joinpath("photo.jpg")
            )

            ctx = WorkflowContext(
                input=WorkflowInput(content=format_pages(pages), images=[photo] if photo else []),
                options=WorkflowOptions(
                    resolve_organizers=job.add_organizers,
                    create_new_organizers=job.add_organizers,
                ),
                repos=self.repos,
                translator=self.translator,
                ai=self.ai,
                user=self.user,
                household=self.household,
            )
            steps: list[WorkflowStep] = [BuildRecipeFromPdfStep(location.name, pages, page_images)]
            if job.add_organizers:
                steps.append(ResolveOrganizersStep())

            try:
                result = await RecipeImportWorkflow(steps).run(ctx)
            except Exception as e:
                if reason := self._stop_reason(e):
                    raise ImportStoppedError(reason) from e
                raise

            recipe = await finalize_scraped_recipe(result.recipe, self.translator)
            recipe.tags = [*(existing for existing in recipe.tags or [] if existing.id != tag.id), tag]
            recipe.notes = [
                *(recipe.notes or []),
                RecipeNote(
                    title=self.t("recipe.pdf-import.source-note-title"),
                    text=self.t("recipe.pdf-import.source-note", name=job.cookbook_name, page=location.first_page),
                ),
            ]
            recipe.extras = {
                **(recipe.extras or {}),
                PDF_SOURCE_EXTRA: _source_value(job.fingerprint, location.first_page),
            }

            created = self.create_one(recipe)
            if photo:
                try:
                    RecipeDataService(created.id).write_image(photo, "jpg")
                    created.image = self.group_recipes.update_image(created.slug)
                except Exception:
                    # the recipe is fine without it
                    self.logger.exception(f"Failed to save the photo for {created.slug}")

            return created

    def _stop_reason(self, error: BaseException) -> str | None:
        """Returns why the import can't go on after an error, or None if it can."""

        import openai

        from mealie.services.openai import chatgpt

        if isinstance(error, exceptions.RateLimitError):
            return self.t("recipe.pdf-import.stopped-usage-limit")

        cause = error.__cause__ or error
        if isinstance(cause, chatgpt.ChatGPTAuthError | OpenAINotEnabledException | openai.AuthenticationError):
            return self.t("recipe.pdf-import.stopped-provider-error")

        return None

    # =======================================================================
    # Organizers and bookkeeping

    def _imported_pages(self, fingerprint: str) -> set[int]:
        """Pages of this PDF whose recipes are already in the group"""

        prefix = _source_prefix(fingerprint)
        pages: set[int] = set()
        for value in self.group_recipes.get_extras_values(PDF_SOURCE_EXTRA, prefix):
            number = value.removeprefix(prefix)
            if number.isdigit():
                pages.add(int(number))
        return pages

    def _cookbook_tag(self, name: str) -> RecipeTag:
        return OrganizerResolver(self.repos).resolve_tags([name], create_missing=True)[0]

    def _add_cookbook(self, name: str, tag: RecipeTag) -> None:
        """Adds a cookbook to the sidebar showing the recipes with the cookbook's tag, unless there's one already."""

        query_filter = f'tags.id IN ["{tag.id}"]'
        existing = self.repos.cookbooks.page_all(PaginationQuery(page=1, per_page=-1)).items
        if any(cookbook.query_filter_string == query_filter for cookbook in existing):
            return

        self.repos.cookbooks.create(
            SaveCookBook(
                name=name,
                query_filter_string=query_filter,
                position=len(existing) + 1,
                group_id=self.user.group_id,
                household_id=self.household.id,
            )
        )

    def _add_failure(
        self, job: PdfImportJob, tally: _ImportTally, location: PdfRecipeLocation, error: Exception
    ) -> None:
        tally.failed += 1
        self._add_entry(
            job,
            self.t("recipe.pdf-import.failed", name=location.name, page=location.first_page),
            success=False,
            exception=str(error),
        )

    def _add_entry(self, job: PdfImportJob, message: str, *, success: bool = True, exception: str = "") -> None:
        self.repos.group_report_entries.create(
            ReportEntryCreate(report_id=job.report_id, success=success, message=message, exception=exception)
        )

    def _set_status(self, job: PdfImportJob, status: ReportSummaryStatus) -> None:
        try:
            report = self.repos.group_reports.get_one(job.report_id)
            if report:
                report.status = status
                self.repos.group_reports.update(job.report_id, report)
        except Exception:
            self.logger.exception("Failed to record the outcome of a PDF import")
            self.repos.session.rollback()
