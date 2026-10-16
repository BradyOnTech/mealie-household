import { addDays, getISOWeek } from "date-fns";
import { useUserApi } from "~/composables/api";
import { groceryError, isoLocalDate, mondayFor } from "~/composables/groceries/grocery-utils";
import type { GrocerySuggestionOut, GroceryWeekView } from "~/lib/api/types/grocery";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

export interface WeekDay {
  /** yyyy-MM-dd */
  date: string;
  /** Local noon on that day, safe for formatting. */
  day: Date;
  isToday: boolean;
  isPast: boolean;
  /** Dinner entries in planner order; the first one with a recipe leads. */
  dinners: ReadPlanEntry[];
  sides: ReadPlanEntry[];
}

const SUGGESTED_NIGHTS = 3;

export function parsePlanDay(value: string): Date {
  return new Date(`${value}T12:00:00`);
}

/** The dinner that represents a day: the first with a recipe, otherwise the first note. */
export function leadDinner(day: WeekDay): ReadPlanEntry | undefined {
  return day.dinners.find(entry => entry.recipe) ?? day.dinners[0];
}

/** Everything else served that day, by name. */
export function accompaniments(day: WeekDay): string[] {
  const lead = leadDinner(day);
  return [...day.dinners, ...day.sides]
    .filter(entry => entry !== lead)
    .map(entry => entry.recipe?.name || entry.title || "")
    .filter(Boolean);
}

/**
 * The household's week as the front page shows it: this week's plan through the next six days,
 * the grocery list for the current week, and dinner ideas for open nights.
 */
export function useHouseholdWeek() {
  const api = useUserApi();

  const today = new Date();
  const todayKey = isoLocalDate(today);
  const weekStart = mondayFor(todayKey);
  const rangeEnd = isoLocalDate(addDays(parsePlanDay(todayKey), 6));
  const weekNumber = getISOWeek(today);

  const entries = ref<ReadPlanEntry[]>([]);
  const groceries = ref<GroceryWeekView | null>(null);
  const suggestions = ref<Record<string, GrocerySuggestionOut[]>>({});
  const loading = ref(true);
  const busy = ref(false);
  const error = ref("");

  const days = computed<WeekDay[]>(() => {
    const result: WeekDay[] = [];
    for (let day = parsePlanDay(weekStart); isoLocalDate(day) <= rangeEnd; day = addDays(day, 1)) {
      const date = isoLocalDate(day);
      const onDay = entries.value.filter(entry => entry.date === date);
      result.push({
        date,
        day,
        isToday: date === todayKey,
        isPast: date < todayKey,
        dinners: onDay.filter(entry => entry.entryType === "dinner"),
        sides: onDay.filter(entry => entry.entryType === "side"),
      });
    }
    return result;
  });

  const tonight = computed(() => days.value.find(day => day.isToday)!);
  const earlier = computed(() => days.value.filter(day => day.isPast));
  const ahead = computed(() => days.value.filter(day => !day.isPast && !day.isToday));
  /** Days of the current calendar week, for the dateline summary. */
  const thisWeek = computed(() => days.value.slice(0, 7));

  async function loadPlan() {
    const { data } = await api.mealplans.getAll(1, -1, { start_date: weekStart, end_date: rangeEnd });
    entries.value = data?.items ?? [];
  }

  async function loadGroceries() {
    const { data } = await api.groceries.week(weekStart);
    groceries.value = data ?? null;
  }

  async function loadSuggestions() {
    const open = days.value.filter(day => !day.isPast && !day.dinners.length).slice(0, SUGGESTED_NIGHTS);
    const results = await Promise.all(open.map(day => api.groceries.suggestions(day.date)));
    const used = new Set<string>();
    const next: Record<string, GrocerySuggestionOut[]> = {};
    open.forEach((day, index) => {
      const fresh = (results[index]?.data ?? []).filter(suggestion => !used.has(suggestion.recipe.id ?? ""));
      next[day.date] = fresh;
      if (fresh[0]?.recipe.id) {
        used.add(fresh[0].recipe.id);
      }
    });
    suggestions.value = next;
  }

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      await Promise.all([loadPlan(), loadGroceries()]);
      await loadSuggestions();
    }
    catch (cause) {
      error.value = groceryError(cause);
    }
    finally {
      loading.value = false;
    }
  }

  async function planDinner(date: string, recipeId: string) {
    if (busy.value) {
      return false;
    }
    busy.value = true;
    try {
      const { data, error: requestError } = await api.mealplans.createOne({ date, entryType: "dinner", recipeId });
      if (!data) {
        throw requestError;
      }
      await loadPlan();
      await loadSuggestions();
      return true;
    }
    catch (cause) {
      error.value = groceryError(cause);
      return false;
    }
    finally {
      busy.value = false;
    }
  }

  return {
    today,
    weekStart,
    weekNumber,
    days,
    tonight,
    earlier,
    ahead,
    thisWeek,
    groceries,
    suggestions,
    loading,
    busy,
    error,
    load,
    loadGroceries,
    planDinner,
  };
}
