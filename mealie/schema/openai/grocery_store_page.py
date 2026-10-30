from pydantic import Field

from ._base import OpenAIBase


class OpenAIStoreProductPages(OpenAIBase):
    urls: list[str] = Field(
        default_factory=list,
        description=(
            "Addresses of this exact product's own page on the store's website, as seen in search results, "
            "best first, at most three. Empty when it can't be found."
        ),
    )
