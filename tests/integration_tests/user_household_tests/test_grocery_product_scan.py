"""Scanning a package's barcode, or snapping a photo of it, to add a preferred product or to put it on the list."""

import pytest
from fastapi.testclient import TestClient

import mealie.services.household_services.grocery_product_reader as reader_module
from mealie.schema.grocery.grocery import GroceryUnit
from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate
from mealie.schema.openai.grocery_product import OpenAIGroceryProduct
from mealie.services.household_services.grocery_barcodes import PackagedProduct
from mealie.services.household_services.grocery_product_links import PackageSize
from mealie.services.openai import OpenAIService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

MILK_UPC = "078742351865"
MILK_GTIN = "0078742351865"
GREAT_VALUE_MILK = PackagedProduct(
    barcode=MILK_GTIN,
    name="Whole Milk",
    brand="Great Value",
    quantity="1 gallon",
    categories=["dairies", "milks", "whole milks"],
    size=PackageSize(128, GroceryUnit.fluid_ounce),
)


@pytest.fixture
def food_facts(monkeypatch: pytest.MonkeyPatch) -> dict[str, PackagedProduct]:
    """Open Food Facts, knowing only the products put in the returned dict"""

    known: dict[str, PackagedProduct] = {}

    async def look_up_barcode(barcode: str) -> PackagedProduct | None:
        return known.get(barcode)

    monkeypatch.setattr(reader_module, "look_up_barcode", look_up_barcode)
    return known


def add_food(api_client: TestClient, user: TestUser, name: str) -> dict:
    response = api_client.post(api_routes.foods, json={"name": name}, headers=user.token)
    assert response.status_code == 201
    return response.json()


def add_product(api_client: TestClient, user: TestUser, **fields) -> dict:
    response = api_client.post(api_routes.households_groceries_products, json=fields, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def scan(api_client: TestClient, user: TestUser, barcode: str, format: str | None = None):
    return api_client.post(
        api_routes.households_groceries_products_scan_barcode,
        json={"barcode": barcode, "format": format},
        headers=user.token,
    )


def enable_ai(user: TestUser, *, images: bool) -> None:
    provider = user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="test-model", api_key="test-key")
    )
    user.repos.group_ai_provider_settings.update(
        user.repos.group_id,
        AIProviderSettingsUpdate(
            default_provider_id=provider.id, audio_provider_id=None, image_provider_id=provider.id if images else None
        ),
    )


def stub_ai(monkeypatch: pytest.MonkeyPatch, answer: OpenAIGroceryProduct) -> list[dict]:
    calls: list[dict] = []

    async def get_response(self, prompt, message, *args, **kwargs):
        calls.append({"message": message, "attachments": kwargs.get("attachments")})
        return answer

    monkeypatch.setattr(OpenAIService, "get_response", get_response)
    return calls


def test_a_new_barcode_fills_in_a_product(api_client: TestClient, unique_user_fn_scoped: TestUser, food_facts):
    user = unique_user_fn_scoped
    milk = add_food(api_client, user, "milk")
    food_facts[MILK_GTIN] = GREAT_VALUE_MILK

    response = scan(api_client, user, MILK_UPC)

    assert response.status_code == 200
    data = response.json()
    assert data["barcode"] == MILK_GTIN
    assert data["identified"] is True
    assert data["saved"] is None
    draft = data["draft"]
    assert draft["name"] == "Great Value Whole Milk 1 gallon"
    # the store brand says where it's sold
    assert draft["store"] == "walmart"
    assert (draft["packageQuantity"], draft["packageUnit"]) == (128, "fluid_ounce")
    assert draft["food"]["id"] == milk["id"]


def test_a_saved_products_barcode_finds_it_at_once(
    api_client: TestClient, unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch
):
    """Scanning what ran out is mostly scanning what the household already buys, which needs nothing looked up"""

    user = unique_user_fn_scoped
    enable_ai(user, images=False)
    milk = add_food(api_client, user, "milk")
    product = add_product(
        api_client, user, foodId=milk["id"], name="Great Value Whole Milk, 1 gal", store="walmart", barcode=MILK_UPC
    )
    assert product["barcode"] == MILK_GTIN
    looked_up: list[str] = []

    async def look_up_barcode(barcode: str) -> None:
        looked_up.append(barcode)

    monkeypatch.setattr(reader_module, "look_up_barcode", look_up_barcode)
    asked_ai = stub_ai(monkeypatch, OpenAIGroceryProduct(name="Whole Milk"))

    # read off the package as an EAN-13 this time, which is the same code
    data = scan(api_client, user, MILK_GTIN, "EAN-13").json()

    assert data["saved"]["id"] == product["id"]
    assert data["draft"]["name"] == "Great Value Whole Milk, 1 gal"
    assert (looked_up, asked_ai) == ([], [])


def test_a_product_saved_without_its_barcode_is_recognized(
    api_client: TestClient, unique_user_fn_scoped: TestUser, food_facts
):
    user = unique_user_fn_scoped
    milk = add_food(api_client, user, "milk")
    food_facts[MILK_GTIN] = GREAT_VALUE_MILK
    from_a_link = add_product(
        api_client, user, foodId=milk["id"], name="Great Value Whole Vitamin D Milk, 1 gal", store="walmart"
    )
    add_product(api_client, user, foodId=milk["id"], name="Kemps Select Whole Milk", store="cub")

    data = scan(api_client, user, MILK_UPC).json()

    assert data["saved"] is None
    assert data["likelySaved"]["id"] == from_a_link["id"]


def test_an_unknown_barcode_is_kept_for_a_photo_to_identify(
    api_client: TestClient, unique_user_fn_scoped: TestUser, food_facts
):
    data = scan(api_client, unique_user_fn_scoped, "041483022011").json()

    assert data["identified"] is False
    assert data["barcode"] == "0041483022011"
    assert data["draft"]["barcode"] == "0041483022011"
    assert data["draft"]["name"] == ""


@pytest.mark.parametrize("barcode", ["078742351866", "12345", "milk"])
def test_invalid_barcodes_are_refused(api_client: TestClient, unique_user: TestUser, food_facts, barcode: str):
    response = scan(api_client, unique_user, barcode)
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "That isn't a valid UPC or EAN barcode"


def test_ai_picks_the_ingredient_for_a_scanned_product(
    api_client: TestClient, unique_user_fn_scoped: TestUser, food_facts, monkeypatch: pytest.MonkeyPatch
):
    user = unique_user_fn_scoped
    enable_ai(user, images=False)
    milk = add_food(api_client, user, "milk")
    food_facts[MILK_GTIN] = GREAT_VALUE_MILK
    calls = stub_ai(
        monkeypatch, OpenAIGroceryProduct(name="Great Value Whole Milk, 1 gal", brand="Great Value", ingredient="milk")
    )

    draft = scan(api_client, user, MILK_UPC).json()["draft"]

    assert "Product database listing: Whole Milk" in calls[0]["message"]
    assert "Categories: dairies, milks, whole milks" in calls[0]["message"]
    assert draft["name"] == "Great Value Whole Milk, 1 gal"
    assert draft["food"]["id"] == milk["id"]
    assert draft["readWithAi"] is True


def upload_photo(api_client: TestClient, user: TestUser, test_image_jpg: str, **form):
    with open(test_image_jpg, "rb") as photo:
        return api_client.post(
            api_routes.households_groceries_products_scan_photo,
            files={"image": ("package.jpg", photo, "image/jpeg")},
            data=form,
            headers=user.token,
        )


def test_a_photo_of_the_package_is_read_by_ai(
    api_client: TestClient,
    unique_user_fn_scoped: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    test_image_jpg: str,
):
    user = unique_user_fn_scoped
    enable_ai(user, images=True)
    calls = stub_ai(
        monkeypatch,
        OpenAIGroceryProduct(
            name="Friendly Farms Oat Milk, 64 fl oz",
            brand="Friendly Farms",
            ingredient="oat milk",
            package_quantity=64,
            package_unit="fluid_ounce",
        ),
    )

    response = upload_photo(api_client, user, test_image_jpg, barcode="041483022011")

    assert response.status_code == 200
    data = response.json()
    assert calls[0]["attachments"], "the photo should go to the AI"
    assert data["identified"] is True
    assert data["barcode"] == "0041483022011"
    draft = data["draft"]
    assert draft["name"] == "Friendly Farms Oat Milk, 64 fl oz"
    assert draft["store"] == "aldi"
    assert draft["newFoodName"] == "oat milk"
    assert (draft["packageQuantity"], draft["packageUnit"]) == (64, "fluid_ounce")


def test_a_photo_ai_cant_place_is_unidentified(
    api_client: TestClient,
    unique_user_fn_scoped: TestUser,
    monkeypatch: pytest.MonkeyPatch,
    test_image_jpg: str,
):
    user = unique_user_fn_scoped
    enable_ai(user, images=True)
    stub_ai(monkeypatch, OpenAIGroceryProduct(name=""))

    data = upload_photo(api_client, user, test_image_jpg).json()

    assert data["identified"] is False


def test_photos_need_an_ai_that_reads_images(
    api_client: TestClient, unique_user_fn_scoped: TestUser, test_image_jpg: str
):
    user = unique_user_fn_scoped
    enable_ai(user, images=False)

    response = upload_photo(api_client, user, test_image_jpg)

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Reading photos needs an AI provider that can read images"


def test_only_photos_are_read(api_client: TestClient, unique_user: TestUser):
    response = api_client.post(
        api_routes.households_groceries_products_scan_photo,
        files={"image": ("notes.txt", b"milk", "text/plain")},
        headers=unique_user.token,
    )
    assert response.status_code == 415


def test_editing_a_product_keeps_its_barcode_unless_told(api_client: TestClient, unique_user_fn_scoped: TestUser):
    """Older forms don't know about barcodes, so an edit from one mustn't wipe the barcode out."""

    user = unique_user_fn_scoped
    milk = add_food(api_client, user, "milk")
    product = add_product(api_client, user, foodId=milk["id"], name="Milk", store="walmart", barcode=MILK_UPC)
    route = f"{api_routes.households_groceries_products}/{product['id']}"
    fields = {"foodId": milk["id"], "name": "Whole milk", "store": "walmart"}

    kept = api_client.put(route, json=fields, headers=user.token).json()
    assert (kept["name"], kept["barcode"]) == ("Whole milk", MILK_GTIN)

    cleared = api_client.put(route, json={**fields, "barcode": None}, headers=user.token).json()
    assert cleared["barcode"] is None


def test_a_product_with_an_invalid_barcode_is_refused(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    milk = add_food(api_client, user, "milk")
    response = api_client.post(
        api_routes.households_groceries_products,
        json={"foodId": milk["id"], "name": "Milk", "store": "walmart", "barcode": "078742351866"},
        headers=user.token,
    )
    assert response.status_code == 422
