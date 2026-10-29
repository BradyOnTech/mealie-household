import asyncio

from fastapi import HTTPException
from pydantic import UUID4

from mealie.core import exceptions
from mealie.lang.providers import Translator
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import CreateRecipeBulk, CreateRecipeByUrlBulk
from mealie.schema.reports.reports import (
    ReportCategory,
    ReportCreate,
    ReportEntryCreate,
    ReportOut,
    ReportSummaryStatus,
)
from mealie.schema.user.user import GroupInDB
from mealie.services._base_service import BaseService
from mealie.services.openai import OpenAINotEnabledException
from mealie.services.recipe.ai_recipe_service import AIProviderNotEnabledError
from mealie.services.recipe.import_workflow.exceptions import NoRecipeDataError
from mealie.services.recipe.recipe_service import RecipeService
from mealie.services.scraper.scraper import ParserErrors, create_from_html


class RecipeBulkScraperService(BaseService):
    """
    Imports a batch of links in the background, recording each one in a report as soon as it's
    done, so the import page can show the batch's progress while it runs.
    """

    report: ReportOut | None

    def __init__(
        self, service: RecipeService, repos: AllRepositories, group: GroupInDB, translator: Translator
    ) -> None:
        self.service = service
        self.repos = repos
        self.group = group
        self.translator = translator
        self.report = None

        super().__init__()

    def get_report_id(self, count: int | None = None) -> UUID4:
        name = self.translator.t("recipe.bulk-import.report-name", count=count) if count else "Bulk Import"
        import_report = ReportCreate(
            name=name,
            category=ReportCategory.bulk_import,
            status=ReportSummaryStatus.in_progress,
            group_id=self.group.id,
        )

        self.report = self.repos.group_reports.create(import_report)
        return self.report.id

    def _failure_reason(self, error: BaseException) -> str:
        """Why a link couldn't be imported, worded for the person who added it"""

        if isinstance(error, NoRecipeDataError | AIProviderNotEnabledError) and str(error):
            # raised with an already-translated message
            return str(error)
        if isinstance(error, OpenAINotEnabledException):
            return self.translator.t("recipe.import-errors.ai-not-enabled")
        if isinstance(error, exceptions.RateLimitError):
            return self.translator.t("exceptions.rate-limit-error")
        if isinstance(error, exceptions.VideoDownloadError):
            return self.translator.t("recipe.import-errors.video-download-failed")
        if isinstance(error, exceptions.OpenAIServiceError):
            return self.translator.t("recipe.import-errors.ai-request-failed")
        if isinstance(error, HTTPException) and isinstance(error.detail, dict):
            if error.detail.get("details") == ParserErrors.CONNECTION_ERROR:
                return self.translator.t("recipe.import-errors.page-unreachable")
            return self.translator.t("recipe.import-errors.no-recipe-on-page")

        return self.translator.t("recipe.import-errors.unknown-error")

    def _add_entry(self, message: str, *, success: bool, exception: str = "") -> None:
        if self.report is None:
            return

        self.repos.group_report_entries.create(
            ReportEntryCreate(report_id=self.report.id, success=success, message=message, exception=exception)
        )

    async def scrape(self, urls: CreateRecipeByUrlBulk) -> None:
        if self.report is None:
            self.get_report_id(len(urls.imports))
        assert self.report is not None

        sem = asyncio.Semaphore(3)

        async def _do(bulk_url: CreateRecipeBulk) -> bool:
            url = bulk_url.url
            async with sem:
                try:
                    recipe, _ = await create_from_html(
                        url,
                        self.repos,
                        self.translator,
                        organize=urls.organize,
                        create_new_organizers=urls.create_new_organizers,
                    )
                except Exception as e:
                    self.service.logger.error(f"failed to scrape url during bulk url import {url}")
                    self.service.logger.exception(e)
                    self._add_entry(
                        self.translator.t("recipe.bulk-import.failed", url=url),
                        success=False,
                        exception=self._failure_reason(e),
                    )
                    return False

            if bulk_url.tags:
                recipe.tags = list({tag.id: tag for tag in [*(recipe.tags or []), *bulk_url.tags]}.values())

            if bulk_url.categories:
                recipe.recipe_category = list(
                    {cat.id: cat for cat in [*(recipe.recipe_category or []), *bulk_url.categories]}.values()
                )

            try:
                new_recipe = self.service.create_one(recipe)
            except Exception as e:
                self.service.logger.error(f"Failed to save recipe to database during bulk url import {url}")
                self.service.logger.exception(e)
                self._add_entry(
                    self.translator.t("recipe.bulk-import.failed", url=url),
                    success=False,
                    exception=self.translator.t("recipe.import-errors.unknown-error"),
                )
                return False

            self._add_entry(self.translator.t("recipe.bulk-import.imported", name=new_recipe.name), success=True)
            return True

        results = await asyncio.gather(*[_do(bulk_url) for bulk_url in urls.imports], return_exceptions=True)
        succeeded = sum(result is True for result in results)

        if succeeded == len(results):
            status = ReportSummaryStatus.success
        elif succeeded == 0:
            status = ReportSummaryStatus.failure
        else:
            status = ReportSummaryStatus.partial

        # read back with the entries recorded along the way, which an update would otherwise replace
        if report := self.repos.group_reports.get_one(self.report.id):
            report.status = status
            self.report = self.repos.group_reports.update(report.id, report)
