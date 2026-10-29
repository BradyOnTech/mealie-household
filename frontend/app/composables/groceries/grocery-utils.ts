import type { GroceryCommonItemOut, GroceryProductOut, GroceryStore, GroceryUnit } from "~/lib/api/types/grocery";

export const groceryStores: { value: GroceryStore; title: string; color: string }[] = [
  { value: "walmart", title: "Walmart", color: "#0071CE" },
  { value: "cub", title: "Cub Foods", color: "#C62828" },
  { value: "aldi", title: "Aldi", color: "#E57716" },
  { value: "whole_foods", title: "Whole Foods", color: "#00674B" },
];

export const groceryUnits: { value: GroceryUnit; title: string }[] = [
  { value: "count", title: "items" }, { value: "pound", title: "lb" },
  { value: "ounce", title: "oz (weight)" }, { value: "gram", title: "g" },
  { value: "kilogram", title: "kg" }, { value: "cup", title: "cups" },
  { value: "fluid_ounce", title: "fl oz" }, { value: "milliliter", title: "mL" },
  { value: "liter", title: "L" },
];

/** A store's search for a product, to find its page and copy the link from */
export function storeSearchUrl(store: GroceryStore, query: string): string {
  const q = encodeURIComponent(query.trim());
  switch (store) {
    case "walmart": return `https://www.walmart.com/search?q=${q}`;
    case "cub": return `https://www.cub.com/store/cub/s?k=${q}`;
    case "aldi": return `https://www.aldi.us/store/aldi/s?k=${q}`;
    case "whole_foods": return `https://www.wholefoodsmarket.com/search?text=${q}`;
  }
}

export function storeTitle(store?: string | null) {
  return groceryStores.find(item => item.value === store)?.title ?? "Unassigned";
}

export function unitTitle(unit?: string | null) {
  return groceryUnits.find(item => item.value === unit)?.title ?? "";
}

export function detectGroceryStore(value: string): GroceryStore | null {
  try {
    const domain = new URL(value).hostname.toLowerCase();
    const matches = (host: string) => domain === host || domain.endsWith(`.${host}`);
    if (matches("walmart.com")) return "walmart";
    if (matches("cub.com") || matches("cubfoods.com")) return "cub";
    if (matches("aldi.us") || matches("aldi.com")) return "aldi";
    if (matches("wholefoodsmarket.com")) return "whole_foods";
  }
  catch { /* The URL field validates on save. */ }
  return null;
}

export interface CommonItemRow {
  item: GroceryCommonItemOut;
  /** The product the row shows: the one the list would buy, or the best one at the chosen store */
  product: GroceryProductOut;
}

export interface CommonItemAisle {
  /** Empty for ingredients without a label */
  name: string;
  rows: CommonItemRow[];
}

function searchable(text: string) {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/**
 * Common items by aisle: the ones with a product at `store` (any store when it's null) whose ingredient
 * or product names contain every word of `search`. Aisles go alphabetically, with unlabeled ingredients
 * last, and keep the server's order by name.
 */
export function commonItemAisles(items: GroceryCommonItemOut[], store: GroceryStore | null, search: string): CommonItemAisle[] {
  const words = searchable(search).split(/\s+/).filter(Boolean);
  const aisles = new Map<string, CommonItemRow[]>();
  for (const item of items) {
    const products = store ? item.products.filter(product => product.store === store) : item.products;
    const product = products[0];
    if (!product) continue;
    const text = searchable([item.food.name, item.food.pluralName ?? "", ...products.map(each => each.name)].join(" "));
    if (!words.every(word => text.includes(word))) continue;
    const name = item.aisle ?? "";
    aisles.set(name, [...(aisles.get(name) ?? []), { item, product }]);
  }
  return Array.from(aisles, ([name, rows]) => ({ name, rows }))
    .sort((a, b) => Number(!a.name) - Number(!b.name) || a.name.localeCompare(b.name));
}

/**
 * Where to buy a common item that's being added, so it lands on the list where its row showed it: the
 * store being browsed, or the row's own store when the list's trip isn't going there. Otherwise the list
 * picks, the way it does for recipes.
 */
export function commonItemStore(row: CommonItemRow, browsing: GroceryStore | null, trip: GroceryStore[]): GroceryStore | null {
  if (browsing) return browsing;
  return trip.length && !trip.includes(row.product.store) ? row.product.store : null;
}

export function isoLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** A week's Monday as a short date, like "Oct 26" */
export function formatWeek(week: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }).format(new Date(`${week}T12:00:00`));
}

export function mondayFor(date: string): string {
  const value = new Date(`${date}T12:00:00`);
  if (Number.isNaN(value.getTime())) return mondayFor(isoLocalDate(new Date()));
  value.setDate(value.getDate() - (value.getDay() + 6) % 7);
  return isoLocalDate(value);
}

export function groceryError(error: unknown): string {
  const value = error as { response?: { status?: number; data?: { detail?: unknown } }; message?: string };
  const detail = value?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg ?? "Check the entered fields").join(". ");
  }
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  return value?.message ?? "The request could not be completed. Please try again.";
}
