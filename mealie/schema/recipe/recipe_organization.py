from pydantic import UUID4, Field

from mealie.schema._mealie import MealieModel


class RecipeOrganizationPreviewIn(MealieModel):
    recipes: list[str] = Field(min_length=1, max_length=50)


class RecipeOrganizationIn(MealieModel):
    recipe_id: UUID4
    categories: list[str] = Field(default_factory=list, max_length=3)
    tags: list[str] = Field(default_factory=list, max_length=8)
    tools: list[str] = Field(default_factory=list, max_length=8)


class RecipeOrganizationOut(RecipeOrganizationIn):
    name: str
    slug: str
    error: bool = False


class RecipeOrganizationApplyIn(MealieModel):
    recipes: list[RecipeOrganizationIn] = Field(min_length=1, max_length=50)
