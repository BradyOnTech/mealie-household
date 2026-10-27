import { useUserApi } from "~/composables/api";
import type { GroceryCommonItemList } from "~/lib/api/types/grocery";
import { groceryError } from "./grocery-utils";

/**
 * Common items: the ingredients the household has saved products for, to add to the grocery list
 * in one tap. Adding goes through the Out of list, so it works before there's a list for the week.
 */
export function useGroceryCommonItems() {
  const api = useUserApi();
  const common = ref<GroceryCommonItemList | null>(null);
  const loading = ref(false);
  const error = ref("");

  const items = computed(() => common.value?.items ?? []);

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const result = await api.groceries.commonItems();
      if (!result.data) throw result.error;
      common.value = result.data;
    }
    catch (cause) { error.value = groceryError(cause); }
    finally { loading.value = false; }
  }

  return { common, items, loading, error, load };
}
