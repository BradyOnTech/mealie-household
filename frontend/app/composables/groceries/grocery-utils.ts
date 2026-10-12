import type { GroceryStore, GroceryUnit } from "~/lib/api/types/grocery";

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

export function isoLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
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
  return value?.message ?? "The request could not be completed. Please try again.";
}
