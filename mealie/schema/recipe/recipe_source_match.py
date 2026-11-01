from datetime import datetime

from pydantic import UUID4, Field

from mealie.schema._mealie.mealie_model import MealieModel


class RecipeSourceQuery(MealieModel):
    urls: list[str] = Field(default_factory=list, max_length=100)
    """Links to look for among the group's saved recipes"""


class RecipeSourceMatch(MealieModel):
    """A saved recipe that was imported from the same place as a link"""

    url: str
    """The link that was asked about"""
    id: UUID4
    slug: str
    name: str
    created_at: datetime | None = None
