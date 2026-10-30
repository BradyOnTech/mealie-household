"""A scanned product's own page at its store, found by the household's AI: its link, and the store's photo."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import mealie.services.household_services.grocery_product_photos as photos_module
import mealie.services.household_services.grocery_store_pages as store_pages
from mealie.schema.grocery.grocery import GroceryUnit
from mealie.services.household_services.grocery_barcodes import PackagedProduct
from mealie.services.household_services.grocery_product_links import PackageSize
from mealie.services.household_services.grocery_product_photos import ProductPage
from mealie.services.openai import OpenAIService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

GRANOLA_BARCODE = "4061462608377"
ALDI_PAGE = "https://www.aldi.us/store/aldi/products/62750261-coconut-cacao-super-food-granola"
ALDI_PHOTO = "https://d2lnr5mha7bycj.cloudfront.net/product-image/file/large_granola.jpg"


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (600, 600), (40, 110, 90)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):
    """A household AI that searches the web, and finds Aldi's granola page"""
    searched: list[str] = []

    async def ask_ai(group_id, household_id, store, product):
        searched.append(product.barcode)
        return [ALDI_PAGE] if product.barcode == GRANOLA_BARCODE else []

    async def fetch_product_page(url: str):
        if url == ALDI_PAGE:
            title = "Millville Gluten Free Coconut Cacao Superfood Granola Same-Day Delivery or Pickup | ALDI"
            return ProductPage(url=url, html=f"<html><title>{title}</title></html>", photo=ALDI_PHOTO)
        return None

    async def look_up_barcode(barcode: str):
        if barcode != GRANOLA_BARCODE:
            return None
        return PackagedProduct(
            barcode=barcode, name="Coconut Cacao Granola", brand="Millville", size=PackageSize(11, GroceryUnit.ounce)
        )

    async def download_image(url: str):
        return jpeg() if url == ALDI_PHOTO else None

    monkeypatch.setattr(OpenAIService, "can_search_web", lambda self, task: True)
    monkeypatch.setattr(store_pages, "_ask_ai", ask_ai)
    monkeypatch.setattr(store_pages, "fetch_product_page", fetch_product_page)
    monkeypatch.setattr(store_pages, "look_up_barcode", look_up_barcode)
    monkeypatch.setattr(store_pages, "download_image", download_image)
    monkeypatch.setattr(photos_module, "download_image", download_image)
    store_pages._searches.clear()
    yield SimpleNamespace(searched=searched)
    store_pages._searches.clear()


def add_food(api_client: TestClient, user: TestUser) -> str:
    response = api_client.post(api_routes.foods, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    return response.json()["id"]


def product(api_client: TestClient, user: TestUser, product_id: str) -> dict:
    listed = api_client.get(api_routes.households_groceries_products, headers=user.token).json()
    return next(item for item in listed if item["id"] == product_id)


def test_a_scanned_product_is_found_at_its_store(api_client: TestClient, unique_user: TestUser, web):
    response = api_client.post(
        api_routes.households_groceries_products_find_at_store,
        json={"barcode": GRANOLA_BARCODE, "store": "aldi", "name": "Millville Coconut Cacao Granola, 11 oz"},
        headers=unique_user.token,
    )

    assert response.status_code == 200
    found = response.json()
    assert found["url"] == ALDI_PAGE
    assert found["photo"]["source"] == "store"
    shown = api_client.get(
        api_routes.households_groceries_photos_token_size(found["photo"]["token"], "thumb"), headers=unique_user.token
    )
    assert shown.status_code == 200


def test_nothing_is_found_without_an_ai_that_searches_the_web(api_client: TestClient, unique_user: TestUser):
    response = api_client.post(
        api_routes.households_groceries_products_find_at_store,
        json={"barcode": GRANOLA_BARCODE, "store": "aldi"},
        headers=unique_user.token,
    )
    assert (response.status_code, response.json()) == (200, None)


def test_only_a_real_barcode_is_looked_for(api_client: TestClient, unique_user: TestUser, web):
    response = api_client.post(
        api_routes.households_groceries_products_find_at_store,
        json={"barcode": "4061462608378", "store": "aldi"},
        headers=unique_user.token,
    )
    assert response.status_code == 422
    assert web.searched == []


def test_a_product_saved_without_its_link_gets_the_link_and_the_stores_photo(
    api_client: TestClient, unique_user_fn_scoped: TestUser, web
):
    user = unique_user_fn_scoped
    fields = {"foodId": add_food(api_client, user), "name": "Coconut cacao granola", "store": "aldi"}
    saved = api_client.post(
        api_routes.households_groceries_products, json={**fields, "barcode": GRANOLA_BARCODE}, headers=user.token
    ).json()

    # looked for once the reply had gone
    assert saved["url"] is None
    filled = product(api_client, user, saved["id"])
    assert filled["url"] == ALDI_PAGE
    assert (filled["photoSource"], bool(filled["photo"])) == ("store", True)
    assert filled["name"] == "Coconut cacao granola"
    assert web.searched == [GRANOLA_BARCODE]


def test_a_link_someone_gave_is_never_looked_past(api_client: TestClient, unique_user_fn_scoped: TestUser, web):
    user = unique_user_fn_scoped
    fields = {"foodId": add_food(api_client, user), "name": "Granola", "store": "aldi", "barcode": GRANOLA_BARCODE}
    given = "https://www.aldi.us/store/aldi/products/1234567-my-granola"

    saved = api_client.post(api_routes.households_groceries_products, json={**fields, "url": given}, headers=user.token)
    assert product(api_client, user, saved.json()["id"])["url"] == given

    # and taking a link off a product keeps it off
    route = api_routes.households_groceries_products_product_id(saved.json()["id"])
    api_client.put(route, json={**fields, "url": None}, headers=user.token)
    assert product(api_client, user, saved.json()["id"])["url"] is None
    assert web.searched == []


def test_a_barcode_added_later_brings_the_link_but_a_chosen_photo_stays(
    api_client: TestClient, unique_user_fn_scoped: TestUser, web
):
    user = unique_user_fn_scoped
    fields = {"foodId": add_food(api_client, user), "name": "Granola", "store": "aldi"}
    saved = api_client.post(api_routes.households_groceries_products, json=fields, headers=user.token).json()
    token = api_client.post(
        api_routes.households_groceries_photos, files={"image": ("photo.jpg", jpeg(), "image/jpeg")}, headers=user.token
    ).json()["token"]
    chosen = api_client.put(
        api_routes.households_groceries_products_product_id_photo(saved["id"]),
        json={"token": token},
        headers=user.token,
    ).json()
    assert web.searched == []

    route = api_routes.households_groceries_products_product_id(saved["id"])
    api_client.put(route, json={**fields, "barcode": GRANOLA_BARCODE}, headers=user.token)

    filled = product(api_client, user, saved["id"])
    assert filled["url"] == ALDI_PAGE
    assert (filled["photoSource"], filled["photo"]) == ("chosen", chosen["photo"])


def test_a_product_found_nowhere_is_left_as_it_was(api_client: TestClient, unique_user_fn_scoped: TestUser, web):
    user = unique_user_fn_scoped
    fields = {"foodId": add_food(api_client, user), "name": "Kemps milk", "store": "cub", "barcode": "041483022011"}
    saved = api_client.post(api_routes.households_groceries_products, json=fields, headers=user.token).json()

    left = product(api_client, user, saved["id"])
    assert (left["url"], left["photo"]) == (None, None)
    assert web.searched == ["0041483022011"]
