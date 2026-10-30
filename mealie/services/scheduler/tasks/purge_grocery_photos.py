import time
from datetime import timedelta
from shutil import rmtree

from sqlalchemy import select

from mealie.core import root_logger
from mealie.db.db_setup import session_context
from mealie.db.models.household.grocery import GroceryProduct
from mealie.services.household_services.grocery_product_photos import photos_folder, purge_old_drafts


def purge_grocery_photos() -> None:
    """
    Removes draft photos that were never saved with a product, and the photos of products that are gone,
    which deleting an ingredient or a household does without a word to the photos
    """
    logger = root_logger.get_logger()
    root = photos_folder()
    drafts, products = root / "drafts", root / "products"
    for household in drafts.iterdir() if drafts.is_dir() else []:
        if household.is_dir():
            purge_old_drafts(household)
    if not products.is_dir():
        return

    with session_context() as session:
        kept = {str(product_id) for product_id in session.execute(select(GroceryProduct.id)).scalars()}
    # a photo saved since the products were listed is moments old, and isn't touched
    cutoff = time.time() - timedelta(hours=1).total_seconds()
    removed = 0
    for folder in products.iterdir():
        if folder.name not in kept and folder.stat().st_mtime < cutoff:
            rmtree(folder, ignore_errors=True)
            removed += 1
    if removed:
        logger.info(f"Removed the photos of {removed} grocery products that are gone")
