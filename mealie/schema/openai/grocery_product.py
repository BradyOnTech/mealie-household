from pydantic import Field

from ._base import OpenAIBase


class OpenAIGroceryProduct(OpenAIBase):
    name: str = Field(
        "",
        description="The product's name as a shopper knows it, with brand and size, e.g. 'Great Value Milk, 1 gal'.",
    )

    brand: str = Field("", description="The product's brand, e.g. 'Great Value', or empty when it can't be told.")

    ingredient: str = Field(
        "",
        description="What a recipe would call this product, e.g. 'milk' or 'egg', using a supplied name when one fits.",
    )

    package_quantity: float | None = Field(
        None,
        description="How much one package holds, in package_unit, or null when the product doesn't say.",
    )

    package_unit: str | None = Field(
        None,
        description="One of the supplied package units, or null when the product doesn't say.",
    )
