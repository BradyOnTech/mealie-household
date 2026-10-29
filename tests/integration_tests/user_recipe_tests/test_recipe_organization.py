import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.group.ai_providers import AIProviderCreate, AIProviderSettingsUpdate, AITask
from mealie.schema.openai.organizers import OpenAIOrganizers
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_category import TagSave
from mealie.schema.recipe.recipe_ingredient import RecipeIngredient
from mealie.schema.recipe.recipe_notes import RecipeNote
from mealie.schema.recipe.recipe_step import RecipeStep
from mealie.services.openai import OpenAIService
from mealie.services.recipe.recipe_classifier import RecipeClassifier
from mealie.services.scraper.scraper_strategies import RecipeScraperPackage
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

PREVIEW = "/api/recipes/bulk-actions/organize/preview"
APPLY = "/api/recipes/bulk-actions/organize/apply"


@pytest.fixture
def classifier_setup(unique_user_fn_scoped: TestUser, monkeypatch: pytest.MonkeyPatch):
    user = unique_user_fn_scoped
    provider = user.repos.group_ai_providers.create(
        AIProviderCreate(name=random_string(), model="test-model", api_key="test-key")
    )
    user.repos.group_ai_provider_settings.update(
        user.repos.group_id,
        AIProviderSettingsUpdate(default_provider_id=provider.id, audio_provider_id=None, image_provider_id=None),
    )
    calls: list[dict] = []

    def respond(names: OpenAIOrganizers | None, *, fail: bool = False) -> None:
        async def get_response(self, prompt, message, **kwargs):
            calls.append({"prompt": prompt, "message": message, **kwargs})
            if fail:
                raise RuntimeError("provider unavailable")
            return names

        monkeypatch.setattr(OpenAIService, "get_response", get_response)

    respond(OpenAIOrganizers(categories=["Main Dish"], tags=["Chicken"], tools=["Oven"]))
    return user, respond, calls


def create_recipe(user: TestUser) -> Recipe:
    return user.repos.recipes.create(
        Recipe(
            name=f"Lemon chicken {random_string()}",
            user_id=user.user_id,
            household_id=user._household_id,
            group_id=user._group_id,
            total_time="25 minutes",
            recipe_ingredient=[RecipeIngredient(note="Chicken, lemon, olive oil")],
            recipe_instructions=[RecipeStep(text="Roast chicken in the oven on a sheet pan.")],
        )
    )


def test_preview_is_read_only_and_apply_preserves_edits(api_client: TestClient, classifier_setup) -> None:
    user, respond, calls = classifier_setup
    recipe = create_recipe(user)
    respond(OpenAIOrganizers(categories=["main dish"], tags=["chicken", "CHICKEN", "SEO spam"], tools=["oven"]))
    result = api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token)
    assert result.status_code == 200
    suggestion = result.json()[0]
    assert suggestion["tags"] == ["Chicken"]
    assert suggestion["categories"] == ["Main Dish"]
    assert user.repos.tags.get_one("chicken", "slug") is None
    assert user.repos.categories.get_one("main-dish", "slug") is None
    assert user.repos.recipes.get_one(recipe.slug).tags == []

    # A manual edit after preview must survive applying the accepted labels.
    tag = user.repos.tags.create(TagSave(name="Family Favorite", group_id=user._group_id))
    current = user.repos.recipes.get_one(recipe.slug)
    current.description = "Edited since preview"
    current.tags = [tag]
    user.repos.recipes.update(recipe.slug, current)
    payload = {"recipes": [suggestion]}
    assert api_client.post(APPLY, json=payload, headers=user.token).status_code == 200
    assert api_client.post(APPLY, json=payload, headers=user.token).status_code == 200
    updated = user.repos.recipes.get_one(recipe.slug)
    assert updated.description == "Edited since preview"
    assert {tag.name for tag in updated.tags} == {"Family Favorite", "Chicken"}
    assert len(updated.tags) == 2
    assert [category.name for category in updated.recipe_category] == ["Main Dish"]
    assert [tool.name for tool in updated.tools] == ["Oven"]
    assert len(calls) == 1  # Applying uses exactly the reviewed names, with no second AI call.
    assert calls[0]["task"] == AITask.organizer_matching


def test_existing_vocabulary_is_reused(api_client: TestClient, classifier_setup) -> None:
    user, respond, _ = classifier_setup
    existing = user.repos.tags.create(TagSave(name="Family Favorites", group_id=user._group_id))
    recipe = create_recipe(user)
    respond(OpenAIOrganizers(tags=["family favorite", "Family Favorites", "Vegan", "invented"]))
    result = api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token)
    assert result.status_code == 200
    assert result.json()[0]["tags"] == [existing.name]
    assert not user.repos.tags.get_one("family-favorite", "slug")


def test_existing_instagram_recipes_can_review_the_source_category(api_client: TestClient, classifier_setup) -> None:
    user, _, _ = classifier_setup
    recipe = create_recipe(user)
    recipe.org_url = "https://www.instagram.com/reel/saved-video/"
    user.repos.recipes.update(recipe.slug, recipe)
    response = api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token)
    assert response.status_code == 200
    suggestion = response.json()[0]
    assert suggestion["categories"] == ["Main Dish", "Instagram"]
    assert user.repos.categories.get_one("instagram", "slug") is None

    # A removed source suggestion must stay removed when applying a preview.
    suggestion["categories"].remove("Instagram")
    assert api_client.post(APPLY, json={"recipes": [suggestion]}, headers=user.token).status_code == 200
    assert user.repos.categories.get_one("instagram", "slug") is None

    suggestion["categories"].append("Instagram")
    assert api_client.post(APPLY, json={"recipes": [suggestion]}, headers=user.token).status_code == 200
    updated = user.repos.recipes.get_one(recipe.slug)
    assert [category.name for category in updated.recipe_category] == ["Main Dish", "Instagram"]


def test_missing_recipe_preflights_the_entire_batch(api_client: TestClient, classifier_setup) -> None:
    user, _, calls = classifier_setup
    recipe = create_recipe(user)
    assert api_client.post(PREVIEW, json={"recipes": [recipe.slug, "missing"]}, headers=user.token).status_code == 404
    assert calls == []
    payload = {
        "recipes": [
            {"recipeId": str(recipe.id), "tags": ["Chicken"]},
            {"recipeId": str(uuid4()), "tags": ["Pasta"]},
        ]
    }
    assert api_client.post(APPLY, json=payload, headers=user.token).status_code == 404
    assert user.repos.tags.get_one("chicken", "slug") is None
    assert user.repos.recipes.get_one(recipe.slug).tags == []


def test_preview_reports_provider_failures_without_writes(api_client: TestClient, classifier_setup) -> None:
    user, respond, _ = classifier_setup
    recipe = create_recipe(user)
    respond(None, fail=True)
    response = api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token)
    assert response.status_code == 200
    assert response.json()[0]["error"] is True
    assert user.repos.recipes.get_one(recipe.slug).tags == []


def test_preview_requires_ai(api_client: TestClient, unique_user_fn_scoped: TestUser) -> None:
    user = unique_user_fn_scoped
    recipe = create_recipe(user)
    assert api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token).status_code == 400


def test_batch_limits(api_client: TestClient, unique_user: TestUser) -> None:
    for recipes in ([], ["x"] * 51):
        assert api_client.post(PREVIEW, json={"recipes": recipes}, headers=unique_user.token).status_code == 422


def test_organization_checks_group_and_edit_permissions(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser
) -> None:
    recipe = create_recipe(unique_user)
    recipe.settings.locked = True
    unique_user.repos.recipes.update(recipe.slug, recipe)
    for user, expected in ((h2_user, 403), (g2_user, 404)):
        assert api_client.post(PREVIEW, json={"recipes": [recipe.slug]}, headers=user.token).status_code == expected
        payload = {"recipes": [{"recipeId": str(recipe.id), "categories": ["Dessert"]}]}
        assert api_client.post(APPLY, json=payload, headers=user.token).status_code == expected
    assert unique_user.repos.categories.get_one("dessert", "slug") is None


@pytest.mark.asyncio
async def test_classification_keeps_recipe_and_source_context(classifier_setup) -> None:
    user, _, calls = classifier_setup
    recipe = create_recipe(user)
    recipe.notes = [RecipeNote(title="Storage", text="Freeze for up to three months")]
    await RecipeClassifier(user.repos).suggest(recipe, source="Original keywords: Sunday lunch")
    assert "25 minutes" in calls[0]["message"]
    assert "Freeze for up to three months" in calls[0]["message"]
    assert "Original keywords: Sunday lunch" in calls[0]["message"]


def structured_recipe() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": f"Roast chicken {random_string()}",
        "recipeIngredient": ["1 chicken", "1 lemon"],
        "recipeInstructions": ["Roast in the oven on a sheet pan."],
        "recipeCategory": "Dinner",
        "keywords": "Sunday lunch",
        "totalTime": "PT25M",
    }


@pytest.mark.parametrize("organize", [True, False])
def test_structured_imports_classify_independently_of_source_options(
    api_client: TestClient, classifier_setup, organize: bool
) -> None:
    user, _, calls = classifier_setup
    response = api_client.post(
        api_routes.recipes_create_html_or_json,
        json={"data": json.dumps(structured_recipe()), "organize": organize},
        headers=user.token,
    )
    assert response.status_code == 201
    recipe = user.repos.recipes.get_one(response.json())
    assert [tag.name for tag in recipe.tags] == (["Chicken"] if organize else [])
    assert [category.name for category in recipe.recipe_category] == (["Main Dish"] if organize else [])
    assert len(calls) == int(organize)
    if organize:
        assert "Sunday Lunch" in calls[0]["message"]


def test_source_metadata_and_classification_are_merged(api_client: TestClient, classifier_setup) -> None:
    user, _, _ = classifier_setup
    response = api_client.post(
        api_routes.recipes_create_html_or_json,
        json={"data": json.dumps(structured_recipe()), "includeTags": True, "includeCategories": True},
        headers=user.token,
    )
    assert response.status_code == 201
    recipe = user.repos.recipes.get_one(response.json())
    assert {tag.name for tag in recipe.tags} == {"Chicken", "Sunday Lunch"}
    assert {category.name for category in recipe.recipe_category} == {"Main Dish", "Dinner"}


def test_failed_classification_does_not_fail_a_structured_import(api_client: TestClient, classifier_setup) -> None:
    user, respond, _ = classifier_setup
    respond(None, fail=True)
    response = api_client.post(
        api_routes.recipes_create_html_or_json,
        json={"data": json.dumps(structured_recipe())},
        headers=user.token,
    )
    assert response.status_code == 201
    recipe = user.repos.recipes.get_one(response.json())
    assert len(recipe.recipe_ingredient) == 2
    assert recipe.tags == []


def test_bulk_url_imports_preserve_automatic_and_manual_labels(
    api_client: TestClient, classifier_setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _, calls = classifier_setup
    manual = user.repos.tags.create(TagSave(name="Family Favorite", group_id=user._group_id))
    source = structured_recipe()

    async def get_html(url: str) -> str:
        return RecipeScraperPackage.ld_json_to_html(json.dumps(source))

    monkeypatch.setattr("mealie.services.scraper.recipe_scraper.safe_scrape_html", get_html)
    response = api_client.post(
        api_routes.recipes_create_url_bulk,
        json={
            "imports": [
                {"url": "https://example.test/first", "tags": [manual.model_dump(mode="json", by_alias=True)]},
                {"url": "https://example.test/second"},
            ]
        },
        headers=user.token,
    )
    assert response.status_code == 202
    recipes = user.repos.recipes.get_all()
    assert len(recipes) == 2
    assert all([category.name for category in recipe.recipe_category] == ["Main Dish"] for recipe in recipes)
    assert {tag.name for tag in recipes[0].tags} | {tag.name for tag in recipes[1].tags} == {
        "Chicken",
        "Family Favorite",
    }
    assert all("Chicken" in [tag.name for tag in recipe.tags] for recipe in recipes)
    assert len(calls) == 2
