import json
from pathlib import Path

import pytest
from recipe_scrapers import scrape_html

from mealie.lang.providers import get_locale_provider
from mealie.services.scraper import cleaner
from mealie.services.scraper.scraper_strategies import RecipeScraperPackage
from tests import data as test_data

test_cleaner_data = [
    (test_data.json_best_homemade_salsa_recipe, 2),
    (test_data.json_blue_cheese_stuffed_turkey_meatballs_with_raspberry_balsamic_glaze_2, 3),
    (test_data.json_bon_appetit, 8),
    (test_data.json_chunky_apple_cake, 4),
    (test_data.json_dairy_free_impossible_pumpkin_pie, 7),
    (test_data.json_how_to_make_instant_pot_spaghetti, 8),
    (test_data.json_instant_pot_chicken_and_potatoes, 4),
    (test_data.json_instant_pot_kerala_vegetable_stew, 13),
    (test_data.json_jalapeno_popper_dip, 4),
    (test_data.json_microwave_sweet_potatoes_04783, 4),
    (test_data.json_moroccan_skirt_steak_with_roasted_pepper_couscous, 4),
    (test_data.json_pizza_knoblauch_champignon_paprika_vegan_html, 3),
]


@pytest.mark.parametrize("json_file,num_steps", test_cleaner_data)
def test_cleaner_clean(json_file: Path, num_steps):
    translator = get_locale_provider()
    recipe_data = cleaner.clean(json.loads(json_file.read_text()), translator)
    assert len(recipe_data.recipe_instructions or []) == num_steps


def test_clean_scraper_preserves_notes():
    """Regression test: notes must survive the RecipeScraperPackage pipeline (previously dropped silently)."""
    ld_json = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "Test Recipe",
            "recipeIngredient": ["1 cup flour"],
            "recipeInstructions": [{"@type": "HowToStep", "text": "Mix everything together"}],
            "notes": [
                {"title": "Storage Tip", "text": "Keep refrigerated up to 3 days"},
                {"title": "Variation", "text": "Add chili flakes for extra heat"},
            ],
        }
    )
    html = RecipeScraperPackage.ld_json_to_html(ld_json)
    scraped = scrape_html(html, org_url="https://example.com", supported_only=False)
    translator = get_locale_provider()
    strategy = RecipeScraperPackage("https://example.com", translator, None)  # type: ignore[arg-type]

    recipe, _ = strategy.clean_scraper(scraped, "https://example.com")

    assert recipe.notes is not None
    assert len(recipe.notes) == 2
    assert recipe.notes[0].title == "Storage Tip"
    assert recipe.notes[0].text == "Keep refrigerated up to 3 days"
    assert recipe.notes[1].title == "Variation"
    assert recipe.notes[1].text == "Add chili flakes for extra heat"
