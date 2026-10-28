"""
Imports every recipe in a cookbook, from a PDF or an EPUB.

The import runs in two passes:

1. Find the recipes. The pages' text goes to the AI in overlapping chunks, and it lists each recipe
   with the pages it's on.
2. Import them, one AI request per recipe, with the text and an image of each of its pages. The
   recipe's photo is cut out of the book rather than left to the AI.

An EPUB has no pages of its own, so it's cut into pages when it's read (see `epub_document`), and
everything else works the same.

A whole cookbook takes a lot of AI requests, and a ChatGPT subscription provider can hit its plan's
usage limit partway through. So the recipes found in a book are saved (`cookbook_imports`), each
recipe records which of them it is in an API extra, and importing the same book again uses the
saved recipes rather than asking the AI to find them again, and skips the ones that made it in last
time. Asking again could name or count them differently, and a recipe can't be told apart from
another on the same page by anything but its place there.
"""

import asyncio
import hashlib
import shutil
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
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
from mealie.schema.group.ai_providers import AITask
from mealie.schema.household.household import HouseholdInDB
from mealie.schema.openai.pdf_recipes import OpenAIPdfRecipeLocations
from mealie.schema.recipe.recipe import Recipe, RecipeTag
from mealie.schema.recipe.recipe_cookbook_import import CookbookImportCreate, CookbookImportRecipe
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
from .cookbook_document import CookbookDocument, CookbookReadError, open_cookbook
from .pdf_document import PdfPage
from .steps import BuildRecipeFromPdfStep, format_pages

FIND_RECIPES_PROMPT = "recipes.find-pdf-recipes"

PDF_SOURCE_EXTRA = "pdf_source"
"""
API extra recording which of a book's recipes a recipe was imported as: `<sha256>#page=<number>#item=<n>`,
the book, the page the recipe starts on, and its place among the recipes saved as starting there, from 0.
It is named for PDFs, the only books there were at first, and EPUBs use it too.

Older imports recorded just `<sha256>#page=<number>`, or that with `#recipe=<slug of its name>`, from
before the recipes found were saved. See `_resolve_imported` for how they're matched up.
"""

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
"""Group and book fingerprint of every import in progress, so the same book isn't imported twice at once"""


class PdfImportError(Exception):
    """The import couldn't be started. The message is meant for the user."""


class PdfImportInProgressError(PdfImportError):
    """The same book is already being imported."""


class ImportStoppedError(Exception):
    """Ends an import early. The message is meant for the report."""


@dataclass(frozen=True)
class PdfRecipeLocation:
    name: str
    first_page: int
    last_page: int
    item: int = 0
    """Its place among the recipes starting on `first_page`, from 0"""

    @property
    def page_numbers(self) -> range:
        return range(self.first_page, self.last_page + 1)


@dataclass
class _ImportTally:
    imported: int = 0
    failed: int = 0
    stopped: bool = False
    cookbook_added: bool = False
    cookbook_failed: bool = False


@dataclass(frozen=True)
class _SourceMarker:
    """What a recipe's `PDF_SOURCE_EXTRA` says about where in the book it came from."""

    page: int
    item: int | None
    """None for markers from before the recipes found in a book were saved"""
    names: frozenset[str] = frozenset()
    """
    Slugs of the names the recipe might have been found under: its saved name, and for some older
    markers, the name the AI found
    """


@dataclass
class _BookRecipes:
    locations: list[PdfRecipeLocation]
    saved: bool
    """Whether they're the ones saved for the book before, which the recipes imported since are numbered among"""
    unread: set[int]
    """Pages the AI still couldn't look through"""


@dataclass
class _Resolution:
    """Which of a book's recipes are still to be imported."""

    remaining: list[PdfRecipeLocation] = field(default_factory=list)
    skipped: int = 0
    renamed: dict[int, list[PdfRecipeLocation]] = field(default_factory=dict)
    """By page, recipes taken to be imported already by an older import that saved them under other names"""
    ambiguous: dict[int, list[PdfRecipeLocation]] = field(default_factory=dict)
    """By page, recipes left out because there's no telling which of them an older import brought in"""


@dataclass
class PdfImportJob:
    """An import that's been accepted, to be run in the background."""

    report_id: UUID4
    document: CookbookDocument
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
            shutil.rmtree(self.document.path.parent, ignore_errors=True)
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
    """
    Orders newly found recipes by page, dropping duplicates, and numbers the ones that start on the
    same page in the order they were found.
    """

    unique: dict[tuple[int, str], PdfRecipeLocation] = {}
    for location in sorted(locations, key=lambda loc: loc.first_page):
        unique.setdefault((location.first_page, slugify(location.name)), location)

    counts: dict[int, int] = defaultdict(int)
    numbered: list[PdfRecipeLocation] = []
    for location in unique.values():
        numbered.append(replace(location, item=counts[location.first_page]))
        counts[location.first_page] += 1

    return _clip(numbered)


def _clip(locations: Iterable[PdfRecipeLocation]) -> list[PdfRecipeLocation]:
    """Orders recipes by page, ending each before the next one starts."""

    ordered = sorted(locations, key=lambda loc: (loc.first_page, loc.item))
    clipped: list[PdfRecipeLocation] = []
    for location in ordered:
        next_start = next((loc.first_page for loc in ordered if loc.first_page > location.first_page), None)
        last_page = location.last_page if next_start is None else min(location.last_page, next_start - 1)
        clipped.append(replace(location, last_page=max(last_page, location.first_page)))

    return clipped


def _resolve_imported(
    locations: Sequence[PdfRecipeLocation], markers: Iterable[_SourceMarker], *, trust_items: bool = True
) -> _Resolution:
    """
    Works out which recipes were imported before from their recipes' markers.

    A marker with an item names its recipe exactly, as long as the recipes it was numbered among are
    the ones saved for the book (`trust_items`). If they aren't, it's treated like an older marker,
    since the recipes found this time could be numbered differently. An older marker names only a page, so it's matched
    to a recipe on that page by name: the name the AI found, or the recipe's saved name. Any that don't
    match by name were saved under other names, or renamed since. If they're at least as many as the
    recipes on that page not otherwise accounted for, those are all taken to be imported already. If
    they're fewer, some of those recipes were imported and some weren't, with no telling which, so
    they're all left out, to be reported, rather than risk importing one twice.
    """

    items: set[tuple[int, int]] = set()
    older: dict[int, list[frozenset[str]]] = defaultdict(list)
    for marker in markers:
        if marker.item is not None and trust_items:
            items.add((marker.page, marker.item))
        else:
            older[marker.page].append(marker.names)

    resolution = _Resolution()
    by_page: dict[int, list[PdfRecipeLocation]] = defaultdict(list)
    for location in locations:
        by_page[location.first_page].append(location)

    for page, on_page in sorted(by_page.items()):
        candidates = [loc for loc in on_page if (page, loc.item) not in items]
        resolution.skipped += len(on_page) - len(candidates)

        unmatched_markers = list(older.get(page, []))
        unmatched: list[PdfRecipeLocation] = []
        for location in candidates:
            name = slugify(location.name)
            match = next((i for i, names in enumerate(unmatched_markers) if name in names), None)
            if match is None:
                unmatched.append(location)
            else:
                unmatched_markers.pop(match)
                resolution.skipped += 1

        if not unmatched:
            continue
        if not unmatched_markers:
            resolution.remaining.extend(unmatched)
        elif len(unmatched_markers) >= len(unmatched):
            resolution.renamed[page] = unmatched
            resolution.skipped += len(unmatched)
        else:
            resolution.ambiguous[page] = unmatched

    return resolution


def _source_prefix(fingerprint: str) -> str:
    return f"{fingerprint}#page="


def _source_value(fingerprint: str, location: PdfRecipeLocation) -> str:
    return f"{_source_prefix(fingerprint)}{location.first_page}#item={location.item}"


def _format_pages(numbers: Iterable[int]) -> str:
    return ",".join(str(number) for number in sorted(numbers))


def _parse_pages(value: str) -> set[int]:
    return {int(number) for number in value.split(",") if number.strip().isdigit()}


class PdfRecipeImportService(RecipeService):
    """Imports every recipe in a cookbook PDF or EPUB, recording each in a report as it goes."""

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
        path = work_dir.joinpath("cookbook")

        try:
            fingerprint = await asyncio.to_thread(_save_upload, upload, path)
            document = open_cookbook(path)
            await document.check()
        except CookbookReadError as e:
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
            document=document,
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
            self.logger.exception("Cookbook import failed")
            self.repos.session.rollback()
            self._add_entry(job, self.t("recipe.pdf-import.unexpected-error"), success=False, exception=str(e))
        finally:
            self._set_status(job, status)

    async def _import(self, job: PdfImportJob) -> ReportSummaryStatus:
        pages = await job.document.read_pages()
        # Finding and reading recipes can each have their own image provider, or neither one
        find_with_images = self.ai.can_read_images(AITask.cookbook_discovery)
        read_with_images = self.ai.can_read_images(AITask.cookbook_extraction)

        markers = self._source_markers(job.fingerprint)
        try:
            if not any(page.text for page in pages) and not (find_with_images and read_with_images):
                raise ImportStoppedError(self.t("recipe.pdf-import.needs-image-provider"))
            book = await self._book_recipes(job, pages, has_imports=bool(markers), with_images=find_with_images)
        except ImportStoppedError as e:
            self._add_entry(job, str(e), success=False, exception=str(e.__cause__ or ""))
            return ReportSummaryStatus.failure

        locations = book.locations
        if not locations:
            self._add_entry(job, self.t("recipe.pdf-import.no-recipes-found"), success=False)
            return ReportSummaryStatus.failure

        self._add_entry(job, self.t("recipe.pdf-import.found-recipes", count=len(locations), pages=len(pages)))

        resolution = _resolve_imported(locations, markers, trust_items=book.saved)
        if resolution.skipped:
            self._add_entry(job, self.t("recipe.pdf-import.skipped-imported", count=resolution.skipped))
        for page, renamed in resolution.renamed.items():
            names = ", ".join(location.name for location in renamed)
            self._add_entry(job, self.t("recipe.pdf-import.skipped-renamed", page=page, names=names))
        for page, ambiguous in resolution.ambiguous.items():
            names = ", ".join(location.name for location in ambiguous)
            self._add_entry(job, self.t("recipe.pdf-import.skipped-ambiguous", page=page, names=names), success=False)

        tally = _ImportTally()
        if resolution.remaining:
            tag = self._cookbook_tag(job.cookbook_name)
            pages_by_number = {page.number: page for page in pages}
            tally = await self._import_all(
                job, resolution.remaining, pages_by_number, tag, with_images=read_with_images
            )

        if job.add_cookbook and resolution.skipped and not (tally.cookbook_added or tally.cookbook_failed):
            # an earlier import may have stopped, or failed to add the cookbook, after its recipes were in
            self._recover_cookbook(job, tally)

        if not (tally.failed or tally.stopped or tally.cookbook_failed or resolution.ambiguous or book.unread):
            return ReportSummaryStatus.success
        if tally.imported or resolution.skipped or resolution.ambiguous:
            # recipes left out as ambiguous are there because some of them were imported before
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
                self.logger.exception(f"Failed to import the recipe on page {location.first_page} of a cookbook")
                self.repos.session.rollback()
                return e

            tally.imported += 1
            if job.add_cookbook and not (tally.cookbook_added or tally.cookbook_failed):
                # added with the first recipe, so an import that fails outright doesn't leave an empty one
                self._try_add_cookbook(job, tag, tally)
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

    async def _book_recipes(
        self, job: PdfImportJob, pages: Sequence[PdfPage], *, has_imports: bool, with_images: bool
    ) -> _BookRecipes:
        """
        The recipes in the book: the ones saved when it was first imported, or else found by the AI and
        saved. Pages the AI couldn't look through before are looked through again.
        """

        repo = self.repos.cookbook_imports
        saved = repo.get_one(job.fingerprint, key="fingerprint")
        if saved and not has_imports:
            # none of its recipes are left, so there's nothing to keep track of and they can be found afresh
            repo.delete(saved.id)
            saved = None

        if saved is None:
            found, unread = await self._find_recipes(job, pages, with_images=with_images)
            if found:
                self._forget_items(job.fingerprint)
                self._save_book_recipes(job.fingerprint, found, unread)
            return _BookRecipes(found, saved=False, unread=unread)

        locations = [
            PdfRecipeLocation(recipe.name, recipe.first_page, recipe.last_page, recipe.item) for recipe in saved.recipes
        ]
        unread = _parse_pages(saved.unread_pages)
        if unread:
            known = {location.first_page for location in locations}
            found, still_unread = await self._find_recipes(
                job, [page for page in pages if page.number in unread], with_images=with_images
            )
            new = [location for location in found if location.first_page in unread - known]
            locations = _clip([*locations, *new])
            self._save_book_recipes(job.fingerprint, locations, still_unread)
            unread = still_unread

        return _BookRecipes(_clip(locations), saved=True, unread=unread)

    def _forget_items(self, fingerprint: str) -> None:
        """
        Turns markers numbered among recipes no longer saved for the book (say, after restoring only
        some of a backup) into markers of just their page, since the recipes about to be saved in
        their place could be numbered differently. Like any marker of just a page, they're then
        matched by name.
        """

        prefix = _source_prefix(fingerprint)
        replacements: dict[str, str] = {}
        for value in self.group_recipes.get_extras_values(PDF_SOURCE_EXTRA, prefix):
            page, _, rest = value.removeprefix(prefix).partition("#")
            if page.isdigit() and rest.startswith("item="):
                replacements[value] = f"{prefix}{page}"
        self.group_recipes.replace_extras_values(PDF_SOURCE_EXTRA, replacements)

    def _save_book_recipes(self, fingerprint: str, locations: Sequence[PdfRecipeLocation], unread: set[int]) -> None:
        self.repos.cookbook_imports.save(
            CookbookImportCreate(
                group_id=self.user.group_id,
                fingerprint=fingerprint,
                unread_pages=_format_pages(unread),
                recipes=[
                    CookbookImportRecipe(
                        name=location.name,
                        first_page=location.first_page,
                        last_page=location.last_page,
                        item=location.item,
                    )
                    for location in locations
                ],
            )
        )

    async def _find_recipes(
        self, job: PdfImportJob, pages: Sequence[PdfPage], *, with_images: bool
    ) -> tuple[list[PdfRecipeLocation], set[int]]:
        """Asks the AI to find the recipes on the pages. Also returns the pages it couldn't look through."""

        chunks = _chunk_pages(pages, with_images=with_images)
        # a page in two chunks belongs to the later one, which sees more of what follows it
        owners = {page.number: i for i, chunk in enumerate(chunks) for page in chunk}
        prompt = self.ai.get_prompt(FIND_RECIPES_PROMPT)

        found: list[PdfRecipeLocation] = []
        unread: set[int] = set()
        for i, chunk in enumerate(chunks):
            first, last = chunk[0].number, chunk[-1].number
            response: OpenAIPdfRecipeLocations | None = None
            for try_number in (1, 2):
                try:
                    response = await self._find_recipes_in(job.document, chunk, prompt, with_images=with_images)
                    break
                except Exception as e:
                    if reason := self._stop_reason(e):
                        raise ImportStoppedError(reason) from e

                    self.logger.exception(f"Failed to find recipes on pages {first}-{last} of a cookbook")
                    if try_number == 1:
                        # it may have been a passing problem, so give it a moment and try again
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        unread.update(page.number for page in chunk if owners[page.number] == i)
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

        return _settle(found), unread

    async def _find_recipes_in(
        self, document: CookbookDocument, pages: Sequence[PdfPage], prompt: str, *, with_images: bool
    ) -> OpenAIPdfRecipeLocations | None:
        with get_temporary_path() as temp_path:
            # pages without text can only be read from an image of them
            attachments: list[OpenAILocalImage] = []
            for page in pages:
                if with_images and not page.text:
                    dest = temp_path.joinpath(f"page-{page.number}.jpg")
                    if image := await document.render_page(page.number, dest):
                        attachments.append(OpenAILocalImage(filename=image.name, path=image))

            return await self.ai.get_response(
                prompt,
                format_pages(pages),
                response_schema=OpenAIPdfRecipeLocations,
                attachments=attachments or None,
                task=AITask.cookbook_discovery,
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
                    # an EPUB's text is in reading order, so only pages without any need an image
                    if job.document.layout_matters or not page.text:
                        dest = temp_path.joinpath(f"page-{page.number}.jpg")
                        if image := await job.document.render_page(page.number, dest):
                            page_images.append(image)

            photo = await job.document.extract_photo(location.page_numbers, temp_path.joinpath("photo.jpg"))

            ctx = WorkflowContext(
                input=WorkflowInput(content=format_pages(pages), images=[photo] if photo else []),
                options=WorkflowOptions(
                    resolve_organizers=job.add_organizers,
                    # Standard labels may be created; cookbook imports don't invent a vocabulary.
                    create_new_organizers=False,
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
                    text=self._source_note(job, location),
                ),
            ]
            recipe.extras = {
                **(recipe.extras or {}),
                PDF_SOURCE_EXTRA: _source_value(job.fingerprint, location),
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

    def _source_note(self, job: PdfImportJob, location: PdfRecipeLocation) -> str:
        if job.document.format == "epub":
            # its pages are cut when it's read, so they don't match the pages of any reader
            return self.t("recipe.pdf-import.source-note-book", name=job.cookbook_name)
        return self.t("recipe.pdf-import.source-note", name=job.cookbook_name, page=location.first_page)

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

    def _source_markers(self, fingerprint: str) -> list[_SourceMarker]:
        """The markers of the recipes in the group imported from this book"""

        prefix = _source_prefix(fingerprint)
        markers: list[_SourceMarker] = []
        for value, saved_name in self.group_recipes.get_extras_with_recipe_names(PDF_SOURCE_EXTRA, prefix):
            page, _, rest = value.removeprefix(prefix).partition("#")
            if not page.isdigit():
                continue

            kind, _, identifier = rest.partition("=")
            names = {slugify(saved_name or "")}
            item: int | None = None
            if kind == "item" and identifier.isdigit():
                item = int(identifier)
            elif kind == "recipe":
                names.add(identifier)
            markers.append(_SourceMarker(int(page), item, frozenset(name for name in names if name)))

        return markers

    def _cookbook_tag(self, name: str) -> RecipeTag:
        return OrganizerResolver(self.repos).resolve_tags([name], create_missing=True)[0]

    def _try_add_cookbook(self, job: PdfImportJob, tag: RecipeTag, tally: _ImportTally) -> None:
        """Adds the cookbook, reporting rather than raising if it can't, since its recipes are in all the same."""

        try:
            self._add_cookbook(job.cookbook_name, tag)
            tally.cookbook_added = True
        except Exception as e:
            self.logger.exception("Failed to add the cookbook for a cookbook import")
            self.repos.session.rollback()
            tally.cookbook_failed = True
            self._add_entry(
                job,
                self.t("recipe.pdf-import.cookbook-failed", name=job.cookbook_name),
                success=False,
                exception=str(e),
            )

    def _recover_cookbook(self, job: PdfImportJob, tally: _ImportTally) -> None:
        """Adds the cookbook for recipes imported earlier, if any of them have its tag."""

        tags = OrganizerResolver(self.repos).resolve_tags([job.cookbook_name], create_missing=False)
        if not tags:
            return

        tagged = self.group_recipes.page_all(PaginationQuery(page=1, per_page=1), tags=[tags[0].id])
        if tagged.items:
            self._try_add_cookbook(job, tags[0], tally)

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
            self.logger.exception("Failed to record the outcome of a cookbook import")
            self.repos.session.rollback()
