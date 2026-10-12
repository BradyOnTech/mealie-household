import { useUserApi } from "~/composables/api";
import type { GrocerySuggestionOut, GroceryWeekView } from "~/lib/api/types/grocery";
import type { RequestResponse } from "~/lib/api/types/non-generated";
import { groceryError } from "./grocery-utils";

export function useGroceryWeek(weekStart: Ref<string>) {
  const api = useUserApi();
  const view = ref<GroceryWeekView | null>(null);
  const suggestions = ref<GrocerySuggestionOut[]>([]);
  const busy = ref(false);
  const loading = ref(false);
  const error = ref("");
  let requestId = 0;

  function accept(next: GroceryWeekView) {
    if (next.weekStart !== weekStart.value) return;
    if ((next.week?.revision ?? 0) >= (view.value?.week?.revision ?? 0)) view.value = next;
  }

  async function load() {
    const id = ++requestId;
    loading.value = true;
    try {
      const result = await api.groceries.week(weekStart.value);
      if (!result.data) throw result.error;
      if (id === requestId) accept(result.data);
    }
    catch (cause) { error.value = groceryError(cause); }
    finally { if (id === requestId) loading.value = false; }
  }

  async function loadSuggestions() {
    const result = await api.groceries.suggestions(weekStart.value);
    if (result.data) suggestions.value = result.data;
  }

  async function mutate(action: () => Promise<RequestResponse<GroceryWeekView>>) {
    if (busy.value) return false;
    busy.value = true;
    error.value = "";
    try {
      const result = await action();
      if (!result.data) throw result.error;
      accept(result.data);
      return true;
    }
    catch (cause) {
      error.value = groceryError(cause);
      await load();
      return false;
    }
    finally { busy.value = false; }
  }

  watch(weekStart, async () => {
    view.value = null;
    suggestions.value = [];
    error.value = "";
    await Promise.all([load(), loadSuggestions()]);
  });

  return { api, view, suggestions, busy, loading, error, load, loadSuggestions, mutate };
}
