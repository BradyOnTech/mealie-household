"""
Reading a grocery product from its store link.

Store product pages turn away automated readers (Walmart answers with a "Robot or human?" check), but
their links carry the product's name, and usually its size, in the address itself:

    walmart.com/ip/Great-Value-Whole-Vitamin-D-Milk-Gallon-128-fl-oz/10450114
    cub.com/store/cub/products/2793610-cub-milk-whole-1-gl
    aldi.us/store/aldi/products/16902710-friendly-farms-vitamin-d-milk-1-gal
    wholefoodsmarket.com/product/365-by-whole-foods-market-organic-whole-milk-128-fl-oz-b074h56r6v

So the name, store and package size come from the link, with no request to the store. Matching the
product to one of the household's ingredients is done here by name, and better by AI where there is one
(see `grocery_product_reader`).
"""

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from mealie.schema.grocery.grocery import GroceryStore, GroceryUnit
from mealie.schema.recipe.recipe_ingredient import IngredientFood

STORE_HOSTS: dict[GroceryStore, tuple[str, ...]] = {
    GroceryStore.walmart: ("walmart.com",),
    GroceryStore.cub: ("cub.com", "cubfoods.com"),
    GroceryStore.aldi: ("aldi.us", "aldi.com"),
    GroceryStore.whole_foods: ("wholefoodsmarket.com",),
}

# Path segments that never name a product
_NOT_A_NAME = {"ip", "p", "ps", "product", "products", "store", "detail", "sm", "delivery", "planning", "rsid"}
# An ID at either end of a segment: a number ("16902710-", "-10450114"), "-id-00041483022011", or an
# Amazon-style ASIN as Whole Foods uses ("-b074h56r6v")
_LEADING_ID = re.compile(r"^\d{4,}-")
_TRAILING_ID = re.compile(r"(-id-\d+|-\d{5,}|-b0[0-9a-z]{8})$", re.IGNORECASE)
_EXTENSION = re.compile(r"(\.product)?(\.\d+)?\.html?$", re.IGNORECASE)

# Words kept lowercase in a product name: units, and short words inside a name
_UNIT_WORDS = {"oz", "fl", "lb", "lbs", "g", "kg", "mg", "ml", "l", "ct", "gal", "gl", "pk", "qt", "pt", "ea"}
_SMALL_WORDS = {"a", "an", "and", "by", "for", "in", "of", "or", "the", "to", "with"}
_WORD_NUMBERS = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "half": 0.5}

# Units the grocery list works in, and what other units count as. Gallons, quarts and pints become
# fluid ounces, since the list has no unit of its own for them.
_UNITS: list[tuple[str, GroceryUnit, float]] = [
    (r"fl\.? ?oz|fluid ounces?", GroceryUnit.fluid_ounce, 1),
    (r"gal(?:lons?)?|gl", GroceryUnit.fluid_ounce, 128),
    (r"qt|quarts?", GroceryUnit.fluid_ounce, 32),
    (r"pt|pints?", GroceryUnit.fluid_ounce, 16),
    (r"oz|ounces?", GroceryUnit.ounce, 1),
    (r"lbs?|pounds?", GroceryUnit.pound, 1),
    (r"kg|kilograms?", GroceryUnit.kilogram, 1),
    (r"g|grams?", GroceryUnit.gram, 1),
    (r"ml|milliliters?|millilitres?", GroceryUnit.milliliter, 1),
    (r"l|liters?|litres?", GroceryUnit.liter, 1),
    (r"cups?", GroceryUnit.cup, 1),
    (r"ct|count|pk|packs?|pcs?|pieces?", GroceryUnit.COUNT, 1),
]
_UNIT_PATTERN = "|".join(f"(?P<u{index}>{pattern})" for index, (pattern, _, _) in enumerate(_UNITS))
_SIZE = re.compile(rf"(?<![\w.])(?P<amount>\d+(?:\.\d+)?) ?(?:{_UNIT_PATTERN})(?![\w])", re.IGNORECASE)
# Sizes said in words, or with no number at all: "half gallon", "one gallon", "gallon", "dozen"
_WORD_SIZE = re.compile(
    rf"(?<![\w])(?:(?P<count>{'|'.join(_WORD_NUMBERS)}) )?(?P<unit>gallon|dozen)(?![\w])", re.IGNORECASE
)


@dataclass
class PackageSize:
    quantity: float
    unit: GroceryUnit


def store_for_url(url: str) -> GroceryStore | None:
    host = (urlsplit(url).hostname or "").lower()
    for store, hosts in STORE_HOSTS.items():
        if any(host == known or host.endswith(f".{known}") for known in hosts):
            return store
    return None


def _segment_words(segment: str) -> list[str]:
    segment = _EXTENSION.sub("", unquote(segment).strip())
    segment = _TRAILING_ID.sub("", _LEADING_ID.sub("", segment))
    # a decimal written into a link loses its point: "0-5-gal" is half a gallon
    segment = re.sub(r"(^|-)0-(\d)(?=-|$)", r"\g<1>0.\2", segment)
    return [word for word in re.split(r"[-_+\s,]+", segment) if word]


def product_text(url: str) -> str:
    """The product's name as its link spells it, e.g. "Great Value Whole Vitamin D Milk Gallon 128 fl oz"."""

    best: list[str] = []
    for segment in urlsplit(url).path.split("/"):
        if segment.lower() in _NOT_A_NAME:
            continue
        words = _segment_words(segment)
        # a name has words in it, where IDs and category codes are a single token
        if sum(any(char.isalpha() for char in word) for word in words) < 2:
            continue
        # the product comes after its categories, so a later segment wins ties
        if len(words) >= len(best):
            best = words
    return " ".join(best)


def tidy_name(text: str) -> str:
    """Capitalizes a link's words as a product name, leaving units and small words as they are."""

    words = []
    for index, word in enumerate(text.split()):
        lower = word.lower()
        if lower in _UNIT_WORDS or (index and lower in _SMALL_WORDS):
            words.append(lower)
        elif word.islower():
            words.append(word[:1].upper() + word[1:])
        else:
            words.append(word)
    return " ".join(words)


def package_size(text: str) -> PackageSize | None:
    """The package size a product's name gives, in the grocery list's units, preferring the last mention."""

    matches = list(_SIZE.finditer(text))
    if matches:
        match = matches[-1]
        index = next(int(name[1:]) for name, value in match.groupdict().items() if name.startswith("u") and value)
        _, unit, factor = _UNITS[index]
        quantity = round(float(match.group("amount")) * factor, 3)
        return PackageSize(quantity, unit) if quantity > 0 else None

    if word := _WORD_SIZE.search(text):
        count = _WORD_NUMBERS.get((word.group("count") or "one").lower(), 1.0)
        if word.group("unit").lower() == "dozen":
            return PackageSize(count * 12, GroceryUnit.COUNT)
        return PackageSize(round(count * 128, 3), GroceryUnit.fluid_ounce)
    return None


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "toes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def food_names(food: IngredientFood) -> list[str]:
    """Every name a household ingredient goes by"""
    return [name for name in (food.name, food.plural_name, *(alias.name for alias in food.aliases)) if name]


def match_food(text: str, foods: list[IngredientFood]) -> IngredientFood | None:
    """
    The household ingredient a product's name names, by the most specific one that appears in it as whole
    words: "Peanut Butter" is peanut butter rather than butter, and "Large White Eggs" is egg.
    """

    words = [_singular(word) for word in _words(text)]
    if not words:
        return None
    phrase = f" {' '.join(words)} "

    best: tuple[int, int, int] | None = None
    match: IngredientFood | None = None
    for food in foods:
        for name in food_names(food):
            candidate = " ".join(_singular(word) for word in _words(name))
            if not candidate or f" {candidate} " not in phrase:
                continue
            # most words, then the latest in the name, where the noun usually is ("Garlic Bread" is
            # bread), then the longest name
            score = (len(candidate.split()), phrase.rfind(f" {candidate} "), len(candidate))
            if best is None or score > best:
                best, match = score, food
    return match


def candidate_foods(text: str, foods: list[IngredientFood], limit: int = 60) -> list[IngredientFood]:
    """Household ingredients that share a word with the product's name, for the AI to choose from."""

    words = {_singular(word) for word in _words(text) if len(word) > 2}
    shared = {food.id: len(words & {_singular(word) for word in _words(" ".join(food_names(food)))}) for food in foods}
    candidates = [food for food in foods if shared[food.id]]
    # the ones sharing the most words first, so the cut keeps the likeliest
    candidates.sort(key=lambda food: -shared[food.id])
    return candidates[:limit]


# Words that say how much, not what: a product's name with them left out is what it is
_SIZE_WORDS = _UNIT_WORDS | {
    "gallon",
    "gallons",
    "ounce",
    "ounces",
    "pound",
    "pounds",
    "count",
    "pack",
    "packs",
    "dozen",
    "each",
    "half",
}


def name_words(name: str) -> set[str]:
    """A product name's words that say what it is: no sizes, numbers or little words, and singular"""
    return {
        _singular(word)
        for word in _words(name)
        if not any(char.isdigit() for char in word) and word not in _SIZE_WORDS and word not in _SMALL_WORDS
    }


def name_similarity(first: str, second: str) -> float:
    """How alike two product names are, from 0 to 1, by the words they share, sizes aside"""

    a, b = name_words(first), name_words(second)
    return len(a & b) / len(a | b) if a and b else 0.0
