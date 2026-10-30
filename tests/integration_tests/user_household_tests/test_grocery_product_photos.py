"""Photos of preferred products: found for a link or a barcode, snapped or picked, and saved with the product."""

import os
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import mealie.services.household_services.grocery_product_photos as photos_module
import mealie.services.household_services.grocery_product_reader as reader_module
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.grocery_product import OpenAIGroceryProduct
from mealie.services.household_services.grocery_barcodes import PackagedProduct
from mealie.services.openai import OpenAIService
from mealie.services.scheduler.tasks.purge_grocery_photos import purge_grocery_photos
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

ALDI_LINK = "https://www.aldi.us/store/aldi/products/62750261-coconut-cacao-super-food-granola"
ALDI_PHOTO = "https://d2lnr5mha7bycj.cloudfront.net/product-image/file/large_granola.jpg"
OFF_PHOTO = "https://images.openfoodfacts.org/images/products/007/874/235/1865/front_en.3.400.jpg"
MILK = PackagedProduct(barcode="0078742351865", name="Whole Milk", brand="Great Value", image_url=OFF_PHOTO)


def jpeg(size: tuple[int, int] = (600, 900)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (30, 120, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """The images on the web, by address, and Aldi's pages, which show ALDI_PHOTO"""
    images: dict[str, bytes] = {}

    async def download_image(url: str) -> bytes | None:
        return images.get(url)

    async def store_photo_url(url: str) -> str | None:
        return ALDI_PHOTO if url.startswith("https://www.aldi.us/") else None

    monkeypatch.setattr(photos_module, "download_image", download_image)
    monkeypatch.setattr(photos_module, "store_photo_url", store_photo_url)
    return images


@pytest.fixture
def food_facts(monkeypatch: pytest.MonkeyPatch) -> dict[str, PackagedProduct]:
    """Open Food Facts, knowing only the products put in the returned dict"""
    known: dict[str, PackagedProduct] = {}

    async def look_up_barcode(barcode: str) -> PackagedProduct | None:
        return known.get(barcode)

    monkeypatch.setattr(reader_module, "look_up_barcode", look_up_barcode)
    monkeypatch.setattr(photos_module, "look_up_barcode", look_up_barcode)
    return known


def add_product(api_client: TestClient, user: TestUser, **fields) -> dict:
    if "foodId" not in fields:
        food = api_client.post(api_routes.foods, json={"name": random_string()}, headers=user.token)
        assert food.status_code == 201
        fields["foodId"] = food.json()["id"]
    fields = {"name": "Granola", "store": "aldi", **fields}
    response = api_client.post(api_routes.households_groceries_products, json=fields, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def upload(api_client: TestClient, user: TestUser, data: bytes, content_type: str = "image/jpeg"):
    return api_client.post(
        api_routes.households_groceries_photos, files={"image": ("photo.jpg", data, content_type)}, headers=user.token
    )


def attach(api_client: TestClient, user: TestUser, product_id: str, token: str):
    return api_client.put(
        api_routes.households_groceries_products_product_id_photo(product_id), json={"token": token}, headers=user.token
    )


def draft_photo(api_client: TestClient, user: TestUser, token: str, size: str = "thumb"):
    return api_client.get(api_routes.households_groceries_photos_token_size(token, size), headers=user.token)


def product_photo(api_client: TestClient, user: TestUser, product_id: str, size: str = "thumb"):
    return api_client.get(
        api_routes.households_groceries_products_product_id_photo_size(product_id, size), headers=user.token
    )


def photo_folder(product_id: str):
    return photos_module.photos_folder() / "products" / product_id


def test_a_photo_someone_takes_is_saved_with_the_product(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = upload(api_client, user, jpeg((1200, 1800)))
    assert response.status_code == 201
    draft = response.json()
    assert draft["source"] == "chosen"

    # the form shows it before the product is saved
    shown = draft_photo(api_client, user, draft["token"])
    assert (shown.status_code, shown.headers["content-type"]) == (200, "image/webp")

    product = add_product(api_client, user)
    assert product["photo"] is None
    saved = attach(api_client, user, product["id"], draft["token"]).json()
    assert saved["photo"]
    assert saved["photoSource"] == "chosen"

    for size, side in [("thumb", 320), ("photo", 1000)]:
        response = product_photo(api_client, user, product["id"], size)
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]
        with Image.open(BytesIO(response.content)) as image:
            # the whole package, not cropped to fit
            assert max(image.size) == side
            assert image.width / image.height == pytest.approx(2 / 3, abs=0.01)
    # the draft became the product's photo
    assert draft_photo(api_client, user, draft["token"]).status_code == 404


def test_editing_a_product_keeps_its_photo_and_a_new_photo_gets_a_new_address(
    api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    product = add_product(api_client, user)
    first = attach(api_client, user, product["id"], upload(api_client, user, jpeg()).json()["token"]).json()

    route = api_routes.households_groceries_products_product_id(product["id"])
    edited = api_client.put(
        route, json={"foodId": product["foodId"], "name": "Coconut granola", "store": "aldi"}, headers=user.token
    ).json()
    assert (edited["name"], edited["photo"], edited["photoSource"]) == ("Coconut granola", first["photo"], "chosen")
    listed = api_client.get(api_routes.households_groceries_products, headers=user.token).json()
    assert listed[0]["photo"] == first["photo"]

    second = attach(api_client, user, product["id"], upload(api_client, user, jpeg()).json()["token"]).json()
    assert second["photo"] != first["photo"]


def test_a_photo_can_be_removed_and_goes_with_its_product(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    product = add_product(api_client, user)
    attach(api_client, user, product["id"], upload(api_client, user, jpeg()).json()["token"])

    removed = api_client.delete(
        api_routes.households_groceries_products_product_id_photo(product["id"]), headers=user.token
    ).json()
    assert (removed["photo"], removed["photoSource"]) == (None, None)
    assert product_photo(api_client, user, product["id"]).status_code == 404
    assert not photo_folder(product["id"]).exists()

    attach(api_client, user, product["id"], upload(api_client, user, jpeg()).json()["token"])
    assert photo_folder(product["id"]).exists()
    api_client.delete(api_routes.households_groceries_products_product_id(product["id"]), headers=user.token)
    assert not photo_folder(product["id"]).exists()


def test_photos_stay_in_their_household(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    ours = add_product(api_client, unique_user)
    draft = upload(api_client, unique_user, jpeg()).json()["token"]
    attach(api_client, unique_user, ours["id"], upload(api_client, unique_user, jpeg()).json()["token"])
    # the other household shares the group's ingredients, but not its products
    theirs = add_product(api_client, h2_user, foodId=ours["foodId"])

    assert draft_photo(api_client, h2_user, draft).status_code == 404
    assert product_photo(api_client, h2_user, ours["id"]).status_code == 404
    # neither another household's draft nor another household's product will do
    assert attach(api_client, h2_user, theirs["id"], draft).status_code == 404
    other = upload(api_client, h2_user, jpeg()).json()["token"]
    assert attach(api_client, h2_user, ours["id"], other).status_code == 404
    assert draft_photo(api_client, unique_user, draft).status_code == 200


def test_photos_need_signing_in(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    product = add_product(api_client, user)
    token = upload(api_client, user, jpeg()).json()["token"]
    attach(api_client, user, product["id"], token)

    # signing the test's user in left a session cookie, which would sign this request in too
    api_client.cookies.clear()
    response = api_client.get(api_routes.households_groceries_products_product_id_photo_size(product["id"], "thumb"))
    assert response.status_code == 401


def test_only_photos_are_taken(api_client: TestClient, unique_user: TestUser):
    assert upload(api_client, unique_user, b"milk", "text/plain").status_code == 415
    response = upload(api_client, unique_user, b"<html>not a photo</html>")
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "That isn't a photo Mealie can read"


@pytest.mark.parametrize(("token", "status"), [("0" * 32, 404), ("../../../.secret", 422), ("ABC", 422)])
def test_only_a_households_own_drafts_can_be_saved(
    api_client: TestClient, unique_user: TestUser, token: str, status: int
):
    product = add_product(api_client, unique_user)
    assert attach(api_client, unique_user, product["id"], token).status_code == status


def test_a_store_links_photo_is_the_stores(api_client: TestClient, unique_user: TestUser, web: dict[str, bytes]):
    web[ALDI_PHOTO] = jpeg()

    response = api_client.post(
        api_routes.households_groceries_photos_find, json={"url": ALDI_LINK}, headers=unique_user.token
    )

    assert response.status_code == 200
    assert response.json()["source"] == "store"
    assert draft_photo(api_client, unique_user, response.json()["token"]).status_code == 200


def test_a_barcode_finds_open_food_facts_photo_when_the_store_has_none(
    api_client: TestClient, unique_user: TestUser, web: dict[str, bytes], food_facts: dict[str, PackagedProduct]
):
    web[OFF_PHOTO] = jpeg()
    food_facts[MILK.barcode] = MILK
    walmart_link = "https://www.walmart.com/ip/Great-Value-Whole-Milk/10450114"

    response = api_client.post(
        api_routes.households_groceries_photos_find,
        json={"url": walmart_link, "barcode": "078742351865"},
        headers=unique_user.token,
    )

    assert response.json()["source"] == "open_food_facts"


def test_no_photo_found_is_null(
    api_client: TestClient, unique_user: TestUser, web: dict[str, bytes], food_facts: dict[str, PackagedProduct]
):
    find = api_routes.households_groceries_photos_find
    response = api_client.post(find, json={"url": "https://example.com/granola"}, headers=unique_user.token)
    assert (response.status_code, response.json()) == (200, None)
    assert api_client.post(find, json={}, headers=unique_user.token).status_code == 422


def test_a_scanned_package_comes_with_open_food_facts_photo(
    api_client: TestClient, unique_user_fn_scoped: TestUser, web: dict[str, bytes], food_facts
):
    web[OFF_PHOTO] = jpeg()
    food_facts[MILK.barcode] = MILK

    scan = api_client.post(
        api_routes.households_groceries_products_scan_barcode,
        json={"barcode": "078742351865"},
        headers=unique_user_fn_scoped.token,
    ).json()

    assert scan["draft"]["photo"]["source"] == "open_food_facts"


def test_a_saved_products_scan_doesnt_look_for_a_photo(
    api_client: TestClient, unique_user_fn_scoped: TestUser, web: dict[str, bytes], food_facts
):
    user = unique_user_fn_scoped
    web[OFF_PHOTO] = jpeg()
    food_facts[MILK.barcode] = MILK
    add_product(api_client, user, barcode="078742351865")

    scan = api_client.post(
        api_routes.households_groceries_products_scan_barcode, json={"barcode": "078742351865"}, headers=user.token
    ).json()

    assert scan["saved"] is not None
    assert scan["draft"]["photo"] is None


def test_a_snapped_package_is_kept_as_the_products_photo(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch, test_image_jpg: str
):
    user = unique_user_fn_scoped
    provider = user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="test-model", api_key="test-key")
    )
    user.repos.group_ai_provider_settings.update(
        user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=provider.id, audio_provider_id=None, image_provider_id=provider.id
        ),
    )

    async def get_response(self, prompt, message, *args, **kwargs):
        return OpenAIGroceryProduct(name="Kemps Select Whole Milk, 1 gal", brand="Kemps", ingredient="milk")

    monkeypatch.setattr(OpenAIService, "get_response", get_response)

    with open(test_image_jpg, "rb") as photo:
        scan = api_client.post(
            api_routes.households_groceries_products_scan_photo,
            files={"image": ("package.jpg", photo, "image/jpeg")},
            headers=user.token,
        ).json()

    snapshot = scan["draft"]["photo"]
    assert snapshot["source"] == "scan"
    product = add_product(api_client, user)
    assert attach(api_client, user, product["id"], snapshot["token"]).json()["photoSource"] == "scan"


def test_unsaved_drafts_and_the_photos_of_deleted_products_are_cleared_away(
    api_client: TestClient, unique_user_fn_scoped: TestUser
):
    user = unique_user_fn_scoped
    product = add_product(api_client, user)
    attach(api_client, user, product["id"], upload(api_client, user, jpeg()).json()["token"])
    stale, fresh = (upload(api_client, user, jpeg()).json()["token"] for _ in range(2))
    gone = photos_module.photos_folder() / "products" / "00000000-0000-4000-8000-000000000000"
    gone.mkdir(parents=True)

    two_days_ago = time.time() - 2 * 24 * 3600
    drafts = photos_module.photos_folder() / "drafts" / str(user.household_id)
    for folder in [drafts / stale, gone, photo_folder(product["id"])]:
        os.utime(folder, (two_days_ago, two_days_ago))

    purge_grocery_photos()

    assert not (drafts / stale).exists()
    assert (drafts / fresh).exists()
    assert not gone.exists()
    assert photo_folder(product["id"]).exists()
