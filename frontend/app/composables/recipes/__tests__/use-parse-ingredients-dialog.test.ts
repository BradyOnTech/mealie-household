import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { ParsedIngredient, RecipeIngredient } from "~/lib/api/types/recipe";
import { uuid4 } from "../../use-utils";
import { ParseStep, suggestSplit, useParseIngredientsDialog } from "../use-parse-ingredients-dialog";
import type { Parser } from "~/lib/api/user/recipes/recipe";
import { i18n } from "~/tests/setup";

(global as any).uuid4 = uuid4;

const mockError = vi.spyOn((await import("~/composables/use-toast")).alert, "error");

const mockParseIngredients = vi.fn();
const onSave = vi.fn();
const group = ref({
  aiProviderSettings: { aiEnabled: true },
});
vi.stubGlobal("useGroupSelf", vi.fn().mockReturnValue({ group }));

vi.mock("~/composables/api", () => ({
  useUserApi: () => ({
    recipes: { parseIngredients: mockParseIngredients },
  }),
}));

vi.mock("../use-recipe-ingredients", () => ({
  useIngredientTextParser: () => ({
    ingredientToParserString: (ing: RecipeIngredient) => ing.note || "",
    // Enough of the real display text to check what a line will save as
    parseIngredientText: (ing: RecipeIngredient) => [
      ing.quantity || "",
      ing.unit?.name || "",
      ing.food?.name || "",
      ing.note || "",
    ].filter(Boolean).join(" "),
  }),
}));

const preferences = ref({
  parser: "nlp",
  dontShowInfoPage: true,
});
// `useLocalStorage(..., { mergeDefaults: true })` only falls back to the caller's default when
// nothing has been stored yet. `parsingStorageEmpty` models that first-visit case.
let parsingStorageEmpty = false;
let lastDefaultParser: Parser | undefined;
vi.mock("../../use-users/preferences", () => ({
  useParsingPreferences: (defaultParser: Parser = "nlp") => {
    lastDefaultParser = defaultParser;
    if (parsingStorageEmpty) {
      preferences.value.parser = defaultParser;
    }
    return preferences;
  },
}));

const createFood = vi.fn();
const updateFood = vi.fn();
const createUnit = vi.fn();
const updateUnit = vi.fn();
const savedFoods = ["salt", "paprika", "garlic powder", "onion powder", "oregano", "thyme", "garlic", "pepper", "cheese"]
  .map(name => ({ id: `f-${name}`, name, pluralName: null, aliases: [] }));
const savedUnits = [{ id: "unit-teaspoon", name: "teaspoon", pluralName: "teaspoons", abbreviation: "tsp", aliases: [] }];
const foodStore = { store: ref(savedFoods), actions: { createOne: createFood, updateOne: updateFood, refresh: vi.fn() } };
const unitStore = { store: ref(savedUnits), actions: { createOne: createUnit, updateOne: updateUnit, refresh: vi.fn() } };

vi.mock("~/composables/store", async (importOriginal) => {
  const original: object = await importOriginal();
  return {
    ...original,
    useFoodStore: () => foodStore,
    useUnitStore: () => unitStore,
  };
});

const lines = (...notes: string[]) => notes.map((note, i) => ({
  note,
  referenceId: `ref-${i}`,
})) as NoUndefinedField<RecipeIngredient>[];

function parsed(input: string, ingredient: Partial<RecipeIngredient>, confidence = 0.99): ParsedIngredient {
  return { input, confidence: { average: confidence }, ingredient: { referenceId: uuid4(), ...ingredient } as RecipeIngredient };
}

const butterBeans = () => parsed("29 oz butter beans (or any other type of bean)", {
  quantity: 29,
  unit: { id: "unit-ounce", name: "ounce" } as RecipeIngredient["unit"],
  food: { id: "", name: "butter beans" } as RecipeIngredient["food"],
  note: "or any other type of bean",
});

const wrapper = (ingredients: NoUndefinedField<RecipeIngredient>[] = lines("a")) => {
  const TestComponent = defineComponent({
    template: "<div />",
    setup() {
      const x = useParseIngredientsDialog(ingredients, onSave);
      return {
        setParser(parser: Parser) {
          x.parser.value = parser;
        },
        ...x,
      };
    },
  });
  return mount(TestComponent, { props: {} });
};

async function parsedWrapper(results: ParsedIngredient[], ingredients = lines(...results.map(r => r.input || ""))) {
  mockParseIngredients.mockResolvedValueOnce({ data: results });
  const wrapped = wrapper(ingredients);
  await wrapped.vm.parseIngredients();
  return wrapped;
}

describe("useParseIngredientsDialog", () => {
  beforeEach(() => {
    group.value.aiProviderSettings.aiEnabled = true;
    preferences.value = { parser: "nlp", dontShowInfoPage: false };
    parsingStorageEmpty = false;
    lastDefaultParser = undefined;
    i18n.global.locale = "en-US";
    vi.clearAllMocks();
    mockParseIngredients.mockResolvedValue({ data: [] });
    createFood.mockImplementation(async (data: { name: string }) => ({ id: `food-${data.name}`, name: data.name, aliases: [] }));
    createUnit.mockImplementation(async (data: { name: string }) => ({ id: `unit-${data.name}`, name: data.name, aliases: [] }));
    updateFood.mockImplementation(async (data: object) => data);
    updateUnit.mockImplementation(async (data: object) => data);
  });

  describe("parseIngredients", () => {
    test("turns each imported line into a review item, in recipe order", async () => {
      const ingredients = [
        ...lines("29 oz butter beans"),
        { note: "", referencedRecipe: { name: "Pie crust" }, referenceId: "ref-link" },
        { note: "1 tsp salt", referenceId: "ref-salt", title: "Seasoning" },
      ] as NoUndefinedField<RecipeIngredient>[];
      mockParseIngredients.mockResolvedValueOnce({
        data: [butterBeans(), parsed("1 tsp salt", { quantity: 1, food: { id: "f-salt", name: "salt" } as RecipeIngredient["food"] })],
      });
      const wrapped = wrapper(ingredients);

      const promise = wrapped.vm.parseIngredients();
      expect(wrapped.vm.state.step).toBe(ParseStep.LOADING);
      await promise;

      const { items, state } = wrapped.vm;
      expect(state.step).toBe(ParseStep.REVIEW);
      expect(mockParseIngredients).toHaveBeenCalledWith("nlp", ["29 oz butter beans", "1 tsp salt"]);
      expect(items.map(i => i.input)).toEqual(["29 oz butter beans (or any other type of bean)", "", "1 tsp salt"]);
      expect(items[1]!.ingredient.referencedRecipe?.name).toBe("Pie crust");
    });

    test("keeps section titles and reference ids, so instruction links survive", async () => {
      const ingredients = [{ note: "1 tsp salt", referenceId: "ref-salt", title: "Seasoning" }] as NoUndefinedField<RecipeIngredient>[];
      const wrapped = await parsedWrapper([parsed("1 tsp salt", {})], ingredients);
      const ing = wrapped.vm.items[0]!.ingredient;
      expect(ing.title).toBe("Seasoning");
      expect(ing.referenceId).toBe("ref-salt");
    });

    test("holds unsaved unit and food words aside instead of filling the field", async () => {
      const wrapped = await parsedWrapper([parsed("a handful of crackers", {
        quantity: 1,
        unit: { id: "", name: "handful" } as RecipeIngredient["unit"],
        food: { id: "", name: "crackers" } as RecipeIngredient["food"],
      })]);
      const item = wrapped.vm.items[0]!;
      expect(item.unmatchedUnit).toBe("handful");
      expect(item.unmatchedFood).toBe("crackers");
      expect(item.ingredient.unit).toBeUndefined();
      expect(item.ingredient.food).toBeUndefined();
    });

    test("only makes one call at a time", async () => {
      const wrapped = wrapper();
      const first = wrapped.vm.parseIngredients();
      wrapped.vm.parseIngredients();
      await first;
      expect(mockParseIngredients).toHaveBeenCalledOnce();
    });

    test("an empty recipe goes straight to an empty review", async () => {
      const wrapped = wrapper([]);
      await wrapped.vm.parseIngredients();
      expect(wrapped.vm.state.step).toBe(ParseStep.REVIEW);
      expect(wrapped.vm.items).toEqual([]);
      expect(mockParseIngredients).not.toHaveBeenCalled();
    });

    test("shows the error state when the request fails", async () => {
      mockParseIngredients.mockRejectedValueOnce(new Error("boom"));
      const wrapped = wrapper();
      await wrapped.vm.parseIngredients();
      expect(wrapped.vm.state.step).toBe(ParseStep.ERROR);
    });

    test("shows the error state when no data comes back", async () => {
      mockParseIngredients.mockResolvedValueOnce({ data: undefined });
      const wrapped = wrapper();
      await wrapped.vm.parseIngredients();
      expect(wrapped.vm.state.step).toBe(ParseStep.ERROR);
    });
  });

  describe("what needs the user's input", () => {
    test("counts lines with an unsaved food, an unsaved unit, or an unsure split", async () => {
      const wrapped = await parsedWrapper([
        butterBeans(),
        parsed("2 cups flour", { quantity: 2 }, 0.99),
        parsed("salt to taste", { note: "salt to taste" }, 0.4),
        parsed("1 handful nuts", { unit: { id: "", name: "handful" } as RecipeIngredient["unit"] }),
      ]);
      const { items, needsInput, needsInputCount, readyCount, foodUnresolved, unitUnresolved, isUnsure } = wrapped.vm;
      expect(items.map(needsInput)).toEqual([true, false, true, true]);
      expect(foodUnresolved(items[0]!)).toBe(true);
      expect(isUnsure(items[2]!)).toBe(true);
      expect(unitUnresolved(items[3]!)).toBe(true);
      expect(needsInputCount).toBe(3);
      expect(readyCount).toBe(1);
    });

    test("confirming an unsure line makes it ready", async () => {
      const wrapped = await parsedWrapper([parsed("salt to taste", { note: "salt to taste" }, 0.4)]);
      const item = wrapped.vm.items[0]!;
      wrapped.vm.confirm(item);
      expect(wrapped.vm.needsInput(item)).toBe(false);
      expect(wrapped.vm.needsInputCount).toBe(0);
    });

    test("picking an existing food answers the question and offers to remember the words", async () => {
      const wrapped = await parsedWrapper([butterBeans()]);
      const item = wrapped.vm.items[0]!;
      item.ingredient.food = { id: "f-lima", name: "lima beans", aliases: [] } as unknown as RecipeIngredient["food"];
      expect(wrapped.vm.needsInput(item)).toBe(false);
      expect(wrapped.vm.canRemember(item, "food")).toBe(true);
    });
  });

  describe("answering a question", () => {
    test("adding a food creates it once and fills every line that used the same words", async () => {
      const wrapped = await parsedWrapper([
        butterBeans(),
        parsed("1 can Butter Beans", { food: { id: "", name: "Butter Beans" } as RecipeIngredient["food"] }),
      ]);
      const [first, second] = wrapped.vm.items;
      await wrapped.vm.addUnmatched(first!, "food");

      expect(createFood).toHaveBeenCalledOnce();
      expect(first!.ingredient.food?.name).toBe("butter beans");
      expect(second!.ingredient.food?.id).toBe("food-butter beans");
      expect(wrapped.vm.needsInputCount).toBe(0);
    });

    test("adding a unit fills the unit", async () => {
      const wrapped = await parsedWrapper([parsed("1 handful nuts", { unit: { id: "", name: "handful" } as RecipeIngredient["unit"] })]);
      const item = wrapped.vm.items[0]!;
      await wrapped.vm.addUnmatched(item, "unit");
      expect(createUnit).toHaveBeenCalledOnce();
      expect(item.ingredient.unit?.name).toBe("handful");
      expect(item.unmatchedUnit).toBe("");
    });

    test("says so when the food can't be created", async () => {
      createFood.mockResolvedValueOnce(null);
      const wrapped = await parsedWrapper([butterBeans()]);
      const item = wrapped.vm.items[0]!;
      await wrapped.vm.addUnmatched(item, "food");
      expect(mockError).toHaveBeenCalled();
      expect(wrapped.vm.foodUnresolved(item)).toBe(true);
      expect(wrapped.vm.state.busy[item.key]).toBeUndefined();
    });

    test("keeping the words as a note puts them in front of the existing note", async () => {
      const wrapped = await parsedWrapper([butterBeans()]);
      const item = wrapped.vm.items[0]!;
      wrapped.vm.keepAsNote(item, "food");
      expect(item.ingredient.note).toBe("butter beans, or any other type of bean");
      expect(item.unmatchedFood).toBe("");
      expect(wrapped.vm.needsInput(item)).toBe(false);
    });

    test("remembering the words adds them as another name for the chosen food", async () => {
      const wrapped = await parsedWrapper([butterBeans()]);
      const item = wrapped.vm.items[0]!;
      item.ingredient.food = { id: "f-lima", name: "lima beans", aliases: [] } as unknown as RecipeIngredient["food"];
      await wrapped.vm.rememberAsAlias(item, "food");
      expect(updateFood).toHaveBeenCalledWith(expect.objectContaining({ id: "f-lima", aliases: [{ name: "butter beans" }] }));
      expect(item.unmatchedFood).toBe("");
      expect(wrapped.vm.canRemember(item, "food")).toBe(false);
    });

    test("removing a line drops it from the review", async () => {
      const wrapped = await parsedWrapper([butterBeans(), parsed("2 cups flour", { quantity: 2 })]);
      wrapped.vm.remove(wrapped.vm.items[0]!);
      expect(wrapped.vm.items.map(i => i.input)).toEqual(["2 cups flour"]);
    });
  });

  describe("matching words the reader didn't", () => {
    test("drops a leading \"of\" and matches a saved food", async () => {
      const wrapped = await parsedWrapper([parsed("1 tsp of salt", {
        quantity: 1,
        food: { id: "", name: "of salt" } as RecipeIngredient["food"],
      })]);
      const item = wrapped.vm.items[0]!;
      expect(item.ingredient.food?.id).toBe("f-salt");
      expect(item.unmatchedFood).toBe("");
    });

    test("keeps the words without the \"of\" when there's no saved food", async () => {
      const wrapped = await parsedWrapper([parsed("1 tsp of sumac", {
        food: { id: "", name: "of sumac" } as RecipeIngredient["food"],
      })]);
      expect(wrapped.vm.items[0]!.unmatchedFood).toBe("sumac");
    });

    test("matches a unit by its abbreviation", async () => {
      const wrapped = await parsedWrapper([parsed("1 tsp salt", {
        unit: { id: "", name: "tsp" } as RecipeIngredient["unit"],
      })]);
      expect(wrapped.vm.items[0]!.ingredient.unit?.id).toBe("unit-teaspoon");
    });
  });

  describe("suggestSplit", () => {
    const isUnit = (w: string) => ["tsp", "tsp.", "teaspoon", "cup", "cups"].includes(w.toLowerCase());
    const isFood = (w: string) => savedFoods.some(f => f.name === w.toLowerCase());

    test("splits a list of saved foods under one amount", () => {
      expect(suggestSplit("1 tsp of salt, paprika, garlic powder, onion powder, oregano, thyme", isUnit, isFood)).toEqual({
        parts: ["salt", "paprika", "garlic powder", "onion powder", "oregano", "thyme"],
        note: "",
      });
    });

    test("handles \"and\", \"each\" and a trailing qualifier", () => {
      expect(suggestSplit("½ tsp each salt, pepper and thyme, to taste", isUnit, isFood)).toEqual({
        parts: ["salt", "pepper", "thyme"],
        note: "to taste",
      });
    });

    test.each([
      ["a preparation note", "2 cloves garlic, minced"],
      ["alternatives", "1 tsp salt or pepper"],
      ["a dish name", "1 cup mac and cheese"],
      ["a single food", "1 tsp salt"],
      ["long phrases", "1 cup salt, freshly ground black pepper from the mill"],
    ])("leaves %s alone", (_, input) => {
      expect(suggestSplit(input, isUnit, isFood)).toBeNull();
    });
  });

  describe("splitting a line", () => {
    const listLine = () => parsed("1 tsp of salt, paprika, sumac", {
      quantity: 1,
      unit: { id: "unit-teaspoon", name: "teaspoon" } as RecipeIngredient["unit"],
      food: { id: "", name: "of salt" } as RecipeIngredient["food"],
      note: "paprika, sumac",
    });

    test("is suggested, and counts as needing input", async () => {
      const wrapped = await parsedWrapper([listLine()]);
      const item = wrapped.vm.items[0]!;
      expect(item.splitSuggestion?.parts).toEqual(["salt", "paprika", "sumac"]);
      expect(wrapped.vm.needsInput(item)).toBe(true);
    });

    test("makes one line per food with the same amount", async () => {
      const ingredients = [{ note: "1 tsp of salt, paprika, sumac", referenceId: "ref-spices", title: "Rub" }] as NoUndefinedField<RecipeIngredient>[];
      const wrapped = await parsedWrapper([listLine()], ingredients);
      wrapped.vm.splitLine(wrapped.vm.items[0]!);

      const { items } = wrapped.vm;
      expect(items).toHaveLength(3);
      expect(items.map(i => i.ingredient.quantity)).toEqual([1, 1, 1]);
      expect(items.map(i => i.ingredient.unit?.id)).toEqual(["unit-teaspoon", "unit-teaspoon", "unit-teaspoon"]);
      expect(items.map(i => i.ingredient.food?.id)).toEqual(["f-salt", "f-paprika", undefined]);
      expect(items.map(i => i.ingredient.note)).toEqual(["", "", ""]);
      // The first line keeps the original's place; the rest are new
      expect(items[0]!.ingredient.referenceId).toBe("ref-spices");
      expect(items[0]!.ingredient.title).toBe("Rub");
      expect(items[1]!.ingredient.referenceId).not.toBe("ref-spices");
      expect(items[1]!.ingredient.title).toBe("");
      // The unknown one still asks about its food
      expect(items[2]!.unmatchedFood).toBe("sumac");
      expect(wrapped.vm.needsInputCount).toBe(1);
    });

    test("keeping it as one line clears the question", async () => {
      const wrapped = await parsedWrapper([listLine()]);
      const item = wrapped.vm.items[0]!;
      wrapped.vm.keepAsOneLine(item);
      expect(item.splitSuggestion).toBeNull();
      expect(wrapped.vm.items).toHaveLength(1);
    });
  });

  describe("saving", () => {
    test("saves every line, with unanswered words folded into the note", async () => {
      const wrapped = await parsedWrapper([
        butterBeans(),
        parsed("2 cups flour", { quantity: 2, food: { id: "f-flour", name: "flour" } as RecipeIngredient["food"] }),
      ]);
      expect(wrapped.vm.preview(wrapped.vm.items[0]!)).toBe("29 ounce butter beans, or any other type of bean");

      wrapped.vm.save();

      expect(wrapped.vm.state.saveLoading).toBe(true);
      const saved = onSave.mock.calls[0]![0] as RecipeIngredient[];
      expect(saved).toHaveLength(2);
      expect(saved[0]!.food).toBeUndefined();
      expect(saved[0]!.note).toBe("butter beans, or any other type of bean");
      expect(saved[1]!.food?.name).toBe("flour");
    });

    test("doesn't save an empty list", async () => {
      const wrapped = wrapper([]);
      await wrapped.vm.parseIngredients();
      wrapped.vm.save();
      expect(onSave).not.toHaveBeenCalled();
    });
  });

  describe("explainer", () => {
    test("is open until dismissed, and stays dismissed", () => {
      const wrapped = wrapper();
      expect(wrapped.vm.showExplainer).toBe(true);
      wrapped.vm.dismissExplainer();
      expect(wrapped.vm.showExplainer).toBe(false);
      expect(preferences.value.dontShowInfoPage).toBe(true);
      expect(wrapper().vm.showExplainer).toBe(false);
    });
  });

  describe("availableParsers", () => {
    test("shows open ai parser when available", () => {
      const { availableParsers } = wrapper().vm;
      expect(availableParsers.find(p => p.value === "openai")?.hide).toBeFalsy();
    });
    test("hides open ai parser when not available", () => {
      group.value.aiProviderSettings.aiEnabled = false;
      const { availableParsers } = wrapper().vm;
      expect(availableParsers.find(p => p.value === "openai")?.hide).toBe(true);
    });
  });

  test("the chosen reader is remembered", async () => {
    preferences.value.parser = "";
    const wrapped = wrapper();
    expect(wrapped.vm.parser).toBe("nlp");
    wrapped.vm.setParser("openai");
    await wrapped.vm.$nextTick();
    expect(preferences.value.parser).toBe("openai");
  });

  describe("locale-aware parser default", () => {
    test("an English locale with nothing stored keeps the natural language processor", () => {
      parsingStorageEmpty = true;
      const { parser, showNlpLanguageHint } = wrapper().vm;
      expect(lastDefaultParser).toBe("nlp");
      expect(parser).toBe("nlp");
      expect(showNlpLanguageHint).toBe(false);
    });

    test("another locale with nothing stored starts on the brute parser", () => {
      i18n.global.locale = "de-DE";
      parsingStorageEmpty = true;
      const { parser, showNlpLanguageHint } = wrapper().vm;
      expect(lastDefaultParser).toBe("brute");
      expect(parser).toBe("brute");
      expect(showNlpLanguageHint).toBe(false);
    });

    test("a stored preference is never overridden", () => {
      i18n.global.locale = "de-DE";
      preferences.value.parser = "nlp";
      expect(wrapper().vm.parser).toBe("nlp");
    });

    test("the hint appears for a stored nlp preference outside English", () => {
      i18n.global.locale = "de-DE";
      preferences.value.parser = "nlp";
      expect(wrapper().vm.showNlpLanguageHint).toBe(true);
    });

    test("the hint goes away once another parser is picked", async () => {
      i18n.global.locale = "de-DE";
      preferences.value.parser = "nlp";
      const wrapped = wrapper();
      expect(wrapped.vm.showNlpLanguageHint).toBe(true);
      wrapped.vm.setParser("brute");
      await wrapped.vm.$nextTick();
      expect(wrapped.vm.showNlpLanguageHint).toBe(false);
    });
  });
});
