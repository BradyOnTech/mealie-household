from pydantic import Field

from ._base import OpenAIBase


class OpenAIPdfRecipeLocation(OpenAIBase):
    name: str = Field(
        ...,
        description="The recipe's title, in title case.",
    )

    first_page: int = Field(
        ...,
        description="The number of the page the recipe starts on, from that page's marker.",
    )

    last_page: int = Field(
        ...,
        description=(
            "The number of the last page the recipe continues onto, from that page's marker. "
            "The same as first_page for a recipe that fits on one page."
        ),
    )


class OpenAIPdfRecipeLocations(OpenAIBase):
    recipes: list[OpenAIPdfRecipeLocation] = Field(
        default_factory=list,
        description="Every recipe that starts on the given pages, in page order.",
    )
