"""
Reading a grocery product into a draft preferred product, from its store link, its barcode, or a photo of
its package.

Each source fills in what it can: a link names the product and its store, a barcode is looked up in Open
Food Facts, and a photo is read by AI. Where the household has AI, it also tidies the product's name and
picks its ingredient from the household's own, which name matching alone gets wrong for products like
oat milk.

Scans go one step further and say what the household already has: the product saved with that barcode,
or one saved without a barcode that this is probably the same as, so its barcode can be remembered.
They also come with a photo of the package to save with the product: the front of the package as Open
Food Facts has it, or the photo that was snapped. (A link's photo comes from the store's page, which can
be slow, so it's found separately; see `grocery_product_photos`.)
"""

import asyncio
from pathlib import Path

from mealie.core.root_logger import get_logger
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.grocery.grocery import (
    GroceryPhotoSource,
    GroceryProductLookup,
    GroceryProductOut,
    GroceryProductScan,
    GroceryUnit,
)
from mealie.schema.group.ai_providers import AITask
from mealie.schema.openai.grocery_product import OpenAIGroceryProduct
from mealie.schema.recipe.recipe_ingredient import IngredientFood, IngredientFoodSummary
from mealie.services.openai import OpenAIDataInjection, OpenAILocalImage, OpenAIService
from mealie.services.openai.openai import OpenAIAttachment

from .grocery_barcodes import look_up_barcode, store_for_brand
from .grocery_product_links import (
    candidate_foods,
    food_names,
    match_food,
    name_similarity,
    package_size,
    product_text,
    store_for_url,
    tidy_name,
)
from .grocery_product_photos import GroceryProductPhotos, PhotoError

LIKELY_SAME_PRODUCT = 0.5
"""How alike a saved product's name must be to a scan's to be offered as the same product"""

MAX_PHOTO_INGREDIENTS = 1500


class PhotoReadingUnavailableError(Exception):
    """The household has no AI provider that can read photos"""


class GroceryProductReader:
    # Matching a product to an ingredient is the same kind of call as parsing an ingredient, so it runs on
    # whatever provider and model the household chose for that
    task = AITask.ingredient_parsing

    def __init__(
        self, repos: AllRepositories, ai: OpenAIService | None = None, photos: GroceryProductPhotos | None = None
    ) -> None:
        self.repos = repos
        self.ai = ai if ai is not None else OpenAIService(repos)
        self.photos = photos if photos is not None else GroceryProductPhotos(repos)
        self.logger = get_logger()

    @property
    def ai_enabled(self) -> bool:
        settings = self.ai.provider_settings
        return bool(settings and settings.ai_enabled and self.ai.route(self.task))

    @property
    def can_read_photos(self) -> bool:
        return self.ai_enabled and self.ai.can_read_images(self.task)

    # =========================================================
    # Sources

    async def read_link(self, url: str) -> GroceryProductLookup:
        text = product_text(url)
        foods = self.repos.ingredient_foods.get_all()
        size = package_size(text)
        food = match_food(text, foods)
        lookup = GroceryProductLookup(
            url=url,
            name=tidy_name(text),
            store=store_for_url(url),
            package_quantity=size.quantity if size else None,
            package_unit=size.unit if size else None,
            food=IngredientFoodSummary.model_validate(food) if food else None,
        )
        if text:
            await self._ask_ai(lookup, f"Product name from its store link: {text}", text, foods)
        return lookup

    async def scan_barcode(self, barcode: str) -> GroceryProductScan:
        # Most scans are of something the household already buys, as it runs out. Its own product says all
        # there is to know, so that's answered at once, without waiting on the database and the AI
        if saved := self._saved_with(barcode, self._products()):
            draft = GroceryProductLookup(
                url=saved.url,
                barcode=barcode,
                name=saved.name,
                store=saved.store,
                package_quantity=saved.package_quantity,
                package_unit=saved.package_unit,
                food=saved.food,
            )
            return GroceryProductScan(barcode=barcode, identified=True, draft=draft, saved=saved)

        packaged = await look_up_barcode(barcode)
        if packaged is None:
            return self._scan(GroceryProductLookup(barcode=barcode), identified=False)

        foods = self.repos.ingredient_foods.get_all()
        # the most specific category ("whole milks") names the ingredient better than marketing does
        text = " ".join([packaged.listing, *packaged.categories[-1:]])
        food = match_food(text, foods)
        lookup = GroceryProductLookup(
            barcode=barcode,
            name=packaged.listing,
            store=store_for_brand(packaged.brand),
            package_quantity=packaged.size.quantity if packaged.size else None,
            package_unit=packaged.size.unit if packaged.size else None,
            food=IngredientFoodSummary.model_validate(food) if food else None,
        )
        source = "\n".join(
            [
                f"Product database listing: {packaged.name}",
                f"Brand: {packaged.brand or 'unknown'}",
                f"Package size: {packaged.quantity or 'unknown'}",
                f"Categories: {', '.join(packaged.categories) or 'unknown'}",
            ]
        )
        reading = self._ask_ai(lookup, source, text, foods)
        if packaged.image_url:
            _, lookup.photo = await asyncio.gather(reading, self.photos.from_open_food_facts(packaged.image_url))
        else:
            await reading
        return self._scan(lookup, identified=True)

    async def scan_photo(self, image: Path, barcode: str | None = None) -> GroceryProductScan:
        if not self.can_read_photos:
            raise PhotoReadingUnavailableError()

        foods = self.repos.ingredient_foods.get_all()
        lookup = GroceryProductLookup(barcode=barcode)
        await self._ask_ai(
            lookup,
            "A photo of the product's package is attached.",
            "",
            foods,
            attachments=[OpenAILocalImage(filename=image.name, path=image)],
        )
        # the photo of the package is the product's photo too, until there's a better one
        try:
            lookup.photo = await asyncio.to_thread(self.photos.draft, image, GroceryPhotoSource.scan)
        except PhotoError:
            self.logger.warning("A photo of a package was read, but couldn't be kept as the product's photo")
        return self._scan(lookup, identified=bool(lookup.name))

    # =========================================================
    # AI

    async def _ask_ai(
        self,
        lookup: GroceryProductLookup,
        source: str,
        text: str,
        foods: list[IngredientFood],
        attachments: list[OpenAIAttachment] | None = None,
    ) -> None:
        """
        Fills in what the AI reads from the source. A photo has to be read, so its failures are raised;
        for links and barcodes, what's already been read stands, and a provider problem only costs the extras.
        """

        if not self.ai_enabled:
            return
        try:
            await self._read_with_ai(lookup, source, text, foods, attachments)
        except Exception:
            if attachments:
                raise
            self.logger.exception("Couldn't read a grocery product with AI; using what was read without it")

    async def _read_with_ai(
        self,
        lookup: GroceryProductLookup,
        source: str,
        text: str,
        foods: list[IngredientFood],
        attachments: list[OpenAIAttachment] | None,
    ) -> None:
        if text:
            names: list[str] | str = [food.name for food in candidate_foods(text, foods)]
            names = names or "None of the household's ingredients share a word with this product"
            description = "The household's ingredients that might be this product. Use an exact name when one fits"
        else:
            # a photo has no words to narrow the list by, so the AI gets all of it
            names = [food.name for food in foods][:MAX_PHOTO_INGREDIENTS] or "The household has no ingredients yet"
            description = "The household's ingredients. Use an exact name when one fits"

        injections = [
            OpenAIDataInjection(description=description, value=names),
            OpenAIDataInjection(description="Package units", value=[unit.value for unit in GroceryUnit]),
        ]
        store = lookup.store.value.replace("_", " ").title() if lookup.store else "Unknown"
        response = await self.ai.get_response(
            self.ai.get_prompt("household.read-grocery-product", data_injections=injections),
            f"Store: {store}\n{source}",
            response_schema=OpenAIGroceryProduct,
            attachments=attachments,
            task=self.task,
        )
        if response is None:
            return

        lookup.read_with_ai = True
        if name := response.name.strip():
            lookup.name = name[:255]
        if lookup.store is None:
            lookup.store = store_for_brand(response.brand)

        if ingredient := response.ingredient.strip()[:100]:
            key = ingredient.lower()
            food = next((food for food in foods if key in {name.lower() for name in food_names(food)}), None)
            lookup.food = IngredientFoodSummary.model_validate(food) if food else None
            lookup.new_food_name = None if food else ingredient

        # what the link or the database says is what the package says, so it wins over the AI's reading
        units = {unit.value: unit for unit in GroceryUnit}
        if (
            lookup.package_quantity is None
            and response.package_quantity
            and response.package_quantity > 0
            and response.package_unit in units
        ):
            lookup.package_quantity = round(response.package_quantity, 3)
            lookup.package_unit = units[response.package_unit]

    # =========================================================
    # What the household already has

    def _products(self) -> list[GroceryProductOut]:
        return self.repos.grocery_products.get_all(order_by="priority", order_descending=False)

    @staticmethod
    def _saved_with(barcode: str | None, products: list[GroceryProductOut]) -> GroceryProductOut | None:
        """The household's product with a barcode: an enabled one first, and among those its first choice"""

        if not barcode:
            return None
        return next(
            (product for product in sorted(products, key=lambda p: not p.enabled) if product.barcode == barcode),
            None,
        )

    def _scan(self, draft: GroceryProductLookup, identified: bool) -> GroceryProductScan:
        products = self._products()
        saved = self._saved_with(draft.barcode, products)

        likely = None
        if saved is None and draft.food and draft.name:
            scored = [
                (name_similarity(draft.name, product.name), product)
                for product in products
                if product.food_id == draft.food.id and not product.barcode
            ]
            score, best = max(scored, key=lambda pair: pair[0], default=(0.0, None))
            likely = best if score >= LIKELY_SAME_PRODUCT else None

        return GroceryProductScan(
            barcode=draft.barcode, identified=identified, draft=draft, saved=saved, likely_saved=likely
        )
