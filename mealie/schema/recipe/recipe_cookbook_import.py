from pydantic import UUID4, ConfigDict
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.group import CookbookImportModel
from mealie.schema._mealie import MealieModel


class CookbookImportRecipe(MealieModel):
    """A recipe found in a cookbook. `item` is its place among the recipes starting on `first_page`, from 0."""

    name: str
    first_page: int
    last_page: int
    item: int
    model_config = ConfigDict(from_attributes=True)


class CookbookImportCreate(MealieModel):
    group_id: UUID4
    fingerprint: str
    unread_pages: str = ""
    recipes: list[CookbookImportRecipe] = []


class CookbookImportOut(CookbookImportCreate):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [selectinload(CookbookImportModel.recipes)]
