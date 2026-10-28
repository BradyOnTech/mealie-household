from mealie.db.models.group.cookbook_import import CookbookImportModel
from mealie.schema.recipe.recipe_cookbook_import import CookbookImportCreate, CookbookImportOut

from .repository_generic import GroupRepositoryGeneric


class RepositoryCookbookImports(GroupRepositoryGeneric[CookbookImportOut, CookbookImportModel]):
    def save(self, data: CookbookImportCreate) -> CookbookImportOut:
        """
        Saves the recipes found in a cookbook, replacing any saved before for the same file in one
        transaction, so there's never a moment when the recipes imported from it have nothing to refer to.
        """

        existing = self._query_one_or_none(data.fingerprint)
        try:
            if existing:
                self.session.delete(existing)
                self.session.flush()
            new = self.model(session=self.session, **data.model_dump())
            self.session.add(new)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(new)
        return self.schema.model_validate(new)

    def _query_one_or_none(self, fingerprint: str) -> CookbookImportModel | None:
        stmt = self._query().filter_by(**self._filter_builder(fingerprint=fingerprint))
        return self.session.execute(stmt).unique().scalars().one_or_none()
