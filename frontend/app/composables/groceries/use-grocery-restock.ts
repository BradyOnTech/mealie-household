import { useUserApi } from "~/composables/api";
import type { GroceryRestockCreate, GroceryRestockList } from "~/lib/api/types/grocery";
import type { RequestResponse } from "~/lib/api/types/non-generated";
import { groceryError } from "./grocery-utils";

/**
 * The household's Out of list: things they've run out of, which ride on the newest grocery list
 * until bought. State is shared, so every panel on the page, and the grocery list, see one copy.
 */
export function useGroceryRestock() {
  const api = useUserApi();
  const list = useState<GroceryRestockList | null>("grocery-restock", () => null);
  /** Bumped after every change, so a grocery list on the same page knows to reload */
  const version = useState("grocery-restock-version", () => 0);
  const busy = ref(false);
  const loading = ref(false);
  const error = ref("");

  const items = computed(() => list.value?.items ?? []);
  const recentlyBought = computed(() => list.value?.recentlyBought ?? []);

  async function load() {
    loading.value = true;
    try {
      const result = await api.groceries.restock();
      if (!result.data) throw result.error;
      list.value = result.data;
    }
    catch (cause) { error.value = groceryError(cause); }
    finally { loading.value = false; }
  }

  async function mutate(action: () => Promise<RequestResponse<GroceryRestockList>>) {
    busy.value = true;
    error.value = "";
    try {
      const result = await action();
      if (!result.data) throw result.error;
      list.value = result.data;
      version.value++;
      return true;
    }
    catch (cause) {
      error.value = groceryError(cause);
      return false;
    }
    finally { busy.value = false; }
  }

  return {
    list,
    items,
    recentlyBought,
    version,
    busy,
    loading,
    error,
    load,
    add: (data: GroceryRestockCreate) => mutate(() => api.groceries.addRestock(data)),
    update: (id: string, data: GroceryRestockCreate) => mutate(() => api.groceries.updateRestock(id, data)),
    remove: (id: string) => mutate(() => api.groceries.removeRestock(id)),
    setBought: (id: string, bought: boolean) => mutate(() => api.groceries.setRestockBought(id, bought)),
    /** Pick up changes made elsewhere, like by the assistant, and tell the page's grocery list */
    async refresh() {
      await load();
      version.value++;
    },
  };
}
