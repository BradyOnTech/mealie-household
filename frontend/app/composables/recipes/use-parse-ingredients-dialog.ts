import { alert } from "~/composables/use-toast";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { IngredientFood, IngredientUnit, ParsedIngredient, RecipeIngredient } from "~/lib/api/types/recipe";
import type { Parser } from "~/lib/api/user/recipes/recipe";
import { useUserApi } from "../api";
import { useFoodData, useFoodStore, useUnitData, useUnitStore } from "../store";
import { useParsingPreferences } from "../use-users/preferences";
import { useIngredientTextParser } from "./use-recipe-ingredients";

export const enum ParseStep {
  LOADING,
  REVIEW,
  ERROR,
}

/** Below this, the reader isn't sure it split the line correctly, so we ask the user to confirm it */
export const CONFIDENCE_THRESHOLD = 0.85;

/**
 * One imported ingredient line, as the user reviews it.
 *
 * The reader can find a unit or food that isn't saved yet ("oz", "butter beans"). Those words
 * are held in `unmatchedUnit`/`unmatchedFood` while the field itself stays empty, until the user
 * adds them, picks an existing one, or keeps them as part of the note.
 */
export interface ParseReviewItem {
  key: string;
  /** The line exactly as it came in from the import */
  input: string;
  ingredient: RecipeIngredient;
  /** The reader's average confidence, 0-1; undefined when it gave none */
  confidence?: number;
  unmatchedUnit: string;
  unmatchedFood: string;
  /** The user said the split looks right */
  confirmed: boolean;
}

export type ReviewField = "unit" | "food";

export function useParseIngredientsDialog(
  ingredients: NoUndefinedField<RecipeIngredient[]>,
  onSave: (ingredients: NoUndefinedField<RecipeIngredient>[]) => void,
) {
  const { ingredientToParserString, parseIngredientText } = useIngredientTextParser();

  const { group } = useGroupSelf();
  const i18n = useI18n();
  const api = useUserApi();

  const unitStore = useUnitStore();
  const unitData = useUnitData();
  const foodStore = useFoodStore();
  const foodData = useFoodData();

  // The natural language parser is trained on English recipes, so it isn't a sensible default for
  // other languages: it recognises the quantity but leaves the unit in the food name.
  const isEnglishLocale = computed(() => (i18n.locale.value || "").toLowerCase().startsWith("en"));
  const parserPreferences = useParsingPreferences(isEnglishLocale.value ? "nlp" : "brute");
  const parser = ref<Parser>(parserPreferences.value.parser || "nlp");
  const showNlpLanguageHint = computed(() => parser.value === "nlp" && !isEnglishLocale.value);
  /** The "what are these boxes" explainer, open until the user says they've got it */
  const showExplainer = ref(!parserPreferences.value.dontShowInfoPage);
  const availableParsers = computed(() => {
    return [
      {
        text: i18n.t("recipe.parser.natural-language-processor"),
        value: "nlp",
      },
      {
        text: i18n.t("recipe.parser.brute-parser"),
        value: "brute",
      },
      {
        text: i18n.t("recipe.parser.openai-parser"),
        value: "openai",
        hide: !group.value?.aiProviderSettings?.aiEnabled,
      },
    ];
  });

  const items = ref<ParseReviewItem[]>([]);
  const state = reactive({
    step: ParseStep.LOADING,
    saveLoading: false,
    /** Which item is waiting on a create/alias request, and for which field */
    busy: {} as Record<string, ReviewField | undefined>,
  });

  /** Lowercased name -> unit or food created during this review, so one name is only created once */
  const createdUnits = new Map<string, IngredientUnit>();
  const createdFoods = new Map<string, IngredientFood>();

  // ---- What each item still needs ----

  function isRecipeLink(item: ParseReviewItem) {
    return !!item.ingredient.referencedRecipe;
  }

  function unitUnresolved(item: ParseReviewItem) {
    return !!item.unmatchedUnit && !item.ingredient.unit?.id;
  }

  function foodUnresolved(item: ParseReviewItem) {
    return !!item.unmatchedFood && !item.ingredient.food?.id;
  }

  /** The reader wasn't sure and the user hasn't confirmed it yet */
  function isUnsure(item: ParseReviewItem) {
    return !isRecipeLink(item) && !item.confirmed && (item.confidence ?? 0) < CONFIDENCE_THRESHOLD;
  }

  function needsInput(item: ParseReviewItem) {
    return unitUnresolved(item) || foodUnresolved(item) || isUnsure(item);
  }

  /** An existing unit/food was picked for words the reader found, so offer to remember them as another name */
  function canRemember(item: ParseReviewItem, field: ReviewField) {
    const words = field === "unit" ? item.unmatchedUnit : item.unmatchedFood;
    const chosen = field === "unit" ? item.ingredient.unit : item.ingredient.food;
    return !!words && !!chosen?.id && chosen.name.toLowerCase() !== words.toLowerCase();
  }

  const needsInputCount = computed(() => items.value.filter(needsInput).length);
  const readyCount = computed(() => items.value.length - needsInputCount.value);

  /** The ingredient as it would be saved right now, unresolved words folded into the note */
  function toSaved(item: ParseReviewItem): RecipeIngredient {
    const words: string[] = [];
    if (unitUnresolved(item)) {
      words.push(item.unmatchedUnit);
    }
    if (foodUnresolved(item)) {
      words.push(item.unmatchedFood);
    }
    if (!words.length) {
      return item.ingredient;
    }

    const note = (item.ingredient.note || "").trim();
    return {
      ...item.ingredient,
      note: note ? `${words.join(" ")}, ${note}` : words.join(" "),
    };
  }

  /** How the line will read in the recipe once saved */
  function preview(item: ParseReviewItem): string {
    if (isRecipeLink(item)) {
      return item.ingredient.referencedRecipe?.name || item.input;
    }
    return parseIngredientText(toSaved(item), 1, false).trim();
  }

  // ---- Parsing ----

  function toItem(parsed: ParsedIngredient): ParseReviewItem {
    const ingredient = parsed.ingredient;
    let unmatchedUnit = "";
    let unmatchedFood = "";

    const unit = ingredient.unit;
    if (unit && !unit.id && unit.name) {
      unmatchedUnit = unit.name;
      ingredient.unit = undefined;
    }

    const food = ingredient.food;
    if (food && !food.id && food.name) {
      unmatchedFood = food.name;
      ingredient.food = undefined;
    }

    return {
      key: uuid4(),
      input: parsed.input || "",
      ingredient,
      confidence: parsed.confidence?.average ?? undefined,
      unmatchedUnit,
      unmatchedFood,
      confirmed: false,
    };
  }

  /** Choosing a reader and re-reading can both ask at once; only one request runs */
  let parseInFlight = false;

  async function parseIngredients() {
    if (parseInFlight) {
      return;
    }

    items.value = [];
    state.busy = {};
    state.saveLoading = false;
    createdUnits.clear();
    createdFoods.clear();

    if (!ingredients?.length) {
      state.step = ParseStep.REVIEW;
      return;
    }

    state.step = ParseStep.LOADING;
    parseInFlight = true;
    try {
      const toParse = ingredients.filter(ing => !ing.referencedRecipe);
      const { data, error } = await api.recipes.parseIngredients(parser.value, toParse.map(ing => ingredientToParserString(ing)));
      if (error || !data) {
        throw new Error("Failed to parse ingredients");
      }

      const parsedByOriginal = new Map<RecipeIngredient, ParsedIngredient>();
      data.forEach((parsed, index) => {
        const original = toParse[index];
        if (!original) {
          return;
        }
        // The parser returns neither the section title nor the reference id. Keep both, so
        // section headings survive and instruction steps stay linked to their ingredients.
        parsed.ingredient.title = original.title || "";
        if (original.referenceId) {
          parsed.ingredient.referenceId = original.referenceId;
        }
        parsedByOriginal.set(original, parsed);
      });

      // Keep the recipe's order, linked recipes included
      items.value = ingredients.map((original) => {
        const parsed = parsedByOriginal.get(original);
        if (parsed) {
          return toItem(parsed);
        }
        return toItem({ input: original.note || "", confidence: {}, ingredient: original });
      });
      state.step = ParseStep.REVIEW;
    }
    catch (error) {
      console.error("Error parsing ingredients:", error);
      state.step = ParseStep.ERROR;
    }
    finally {
      parseInFlight = false;
    }
  }

  // ---- Answers to the questions on each card ----

  function confirm(item: ParseReviewItem) {
    item.confirmed = true;
  }

  /** Keep the unsaved words as part of the note instead of a unit or food */
  function keepAsNote(item: ParseReviewItem, field: ReviewField) {
    const saved = toSaved({
      ...item,
      unmatchedUnit: field === "unit" ? item.unmatchedUnit : "",
      unmatchedFood: field === "food" ? item.unmatchedFood : "",
    });
    item.ingredient.note = saved.note;
    if (field === "unit") {
      item.unmatchedUnit = "";
    }
    else {
      item.unmatchedFood = "";
    }
  }

  /** Every other line with the same unsaved words gets the same answer */
  function applyToMatching(words: string, field: ReviewField, value: IngredientUnit | IngredientFood) {
    const target = words.toLowerCase();
    for (const other of items.value) {
      if (field === "unit" && other.unmatchedUnit.toLowerCase() === target && !other.ingredient.unit?.id) {
        other.ingredient.unit = value as IngredientUnit;
        other.unmatchedUnit = "";
      }
      if (field === "food" && other.unmatchedFood.toLowerCase() === target && !other.ingredient.food?.id) {
        other.ingredient.food = value as IngredientFood;
        other.unmatchedFood = "";
      }
    }
  }

  async function createUnit(name: string): Promise<IngredientUnit | null> {
    const cached = createdUnits.get(name.toLowerCase());
    if (cached) {
      return cached;
    }
    unitData.reset();
    unitData.data.name = name;
    const created = await unitStore.actions.createOne(unitData.data);
    if (created) {
      createdUnits.set(created.name.toLowerCase(), created);
    }
    return created;
  }

  async function createFood(name: string): Promise<IngredientFood | null> {
    const cached = createdFoods.get(name.toLowerCase());
    if (cached) {
      return cached;
    }
    foodData.reset();
    foodData.data.name = name;
    const created = await foodStore.actions.createOne(foodData.data);
    if (created) {
      createdFoods.set(created.name.toLowerCase(), created);
    }
    return created;
  }

  async function addUnmatched(item: ParseReviewItem, field: ReviewField) {
    const words = field === "unit" ? item.unmatchedUnit : item.unmatchedFood;
    if (!words || state.busy[item.key]) {
      return;
    }

    state.busy[item.key] = field;
    try {
      const created = field === "unit" ? await createUnit(words) : await createFood(words);
      if (!created) {
        alert.error(i18n.t("general.cant-create-permission"));
        return;
      }

      // This item first, then any other line waiting on the same words
      if (field === "unit") {
        item.ingredient.unit = created as IngredientUnit;
        item.unmatchedUnit = "";
      }
      else {
        item.ingredient.food = created as IngredientFood;
        item.unmatchedFood = "";
      }
      applyToMatching(words, field, created);
    }
    finally {
      state.busy[item.key] = undefined;
    }
  }

  /** Save the imported words as another name for the unit/food the user picked */
  async function rememberAsAlias(item: ParseReviewItem, field: ReviewField) {
    if (!canRemember(item, field) || state.busy[item.key]) {
      return;
    }

    const words = field === "unit" ? item.unmatchedUnit : item.unmatchedFood;
    const chosen = (field === "unit" ? item.ingredient.unit : item.ingredient.food) as IngredientUnit | IngredientFood;
    const aliases = [...(chosen.aliases || [])];
    if (!aliases.some(a => a.name.toLowerCase() === words.toLowerCase())) {
      aliases.push({ name: words });
    }

    state.busy[item.key] = field;
    try {
      const updated = field === "unit"
        ? await unitStore.actions.updateOne({ ...(chosen as IngredientUnit), aliases })
        : await foodStore.actions.updateOne({ ...(chosen as IngredientFood), aliases });
      if (!updated) {
        alert.error(i18n.t("events.something-went-wrong"));
        return;
      }

      if (field === "unit") {
        item.ingredient.unit = updated as IngredientUnit;
        item.unmatchedUnit = "";
      }
      else {
        item.ingredient.food = updated as IngredientFood;
        item.unmatchedFood = "";
      }
      applyToMatching(words, field, updated);
    }
    finally {
      state.busy[item.key] = undefined;
    }
  }

  /** The ingredient editor replaced the whole ingredient */
  function updateIngredient(item: ParseReviewItem, ingredient: RecipeIngredient) {
    item.ingredient = ingredient;
  }

  function remove(item: ParseReviewItem) {
    items.value = items.value.filter(i => i.key !== item.key);
  }

  function dismissExplainer() {
    showExplainer.value = false;
    parserPreferences.value.dontShowInfoPage = true;
  }

  function save() {
    if (!items.value.length) {
      return;
    }
    state.saveLoading = true;
    onSave(items.value.map(item => toSaved(item) as NoUndefinedField<RecipeIngredient>));
  }

  watch(parser, () => {
    parserPreferences.value.parser = parser.value;
  });

  return {
    availableParsers,
    parserPreferences,
    parser,
    showNlpLanguageHint,
    showExplainer,
    items,
    state,
    needsInputCount,
    readyCount,
    isRecipeLink,
    unitUnresolved,
    foodUnresolved,
    isUnsure,
    needsInput,
    canRemember,
    preview,
    parseIngredients,
    confirm,
    keepAsNote,
    addUnmatched,
    rememberAsAlias,
    updateIngredient,
    remove,
    dismissExplainer,
    save,
  };
}
