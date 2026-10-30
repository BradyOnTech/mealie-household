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


class OpenAIPackagePhotoCheck(OpenAIBase):
    brand: str = Field(
        "", description="The brand the package in the photo shows, or empty when it shows no package or brand."
    )
    same_product: bool = Field(
        False, description="Whether the photo shows the scanned product: the same brand and the same product."
    )
