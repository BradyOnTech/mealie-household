import { useUserApi } from "~/composables/api";
import type { GroceryFoodRuleOut, GroceryProductOut } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";
import { groceryError } from "./grocery-utils";

export function useGroceryCatalog() {
  const api = useUserApi();
  const products = ref<GroceryProductOut[]>([]);
  const rules = ref<GroceryFoodRuleOut[]>([]);
  const foods = ref<IngredientFood[]>([]);
  const error = ref("");
  const loading = ref(false);

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [productResult, ruleResult, foodResult] = await Promise.all([
        api.groceries.products(), api.groceries.rules(), api.foods.getAll(),
      ]);
      if (!productResult.data) throw productResult.error;
      if (!ruleResult.data) throw ruleResult.error;
      if (!foodResult.data) throw foodResult.error;
      products.value = productResult.data;
      rules.value = ruleResult.data;
      foods.value = foodResult.data.items;
    }
    catch (cause) { error.value = groceryError(cause); }
    finally { loading.value = false; }
  }

  return { api, products, rules, foods, error, loading, load };
}
