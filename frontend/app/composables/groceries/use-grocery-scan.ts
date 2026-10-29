import type { ScannerResult } from "~/components/Domain/Grocery/GroceryScanner.vue";
import { useUserApi } from "~/composables/api";
import { useGroupSelf } from "~/composables/use-groups";
import type { GroceryProductScan } from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";

/**
 * What a scan turned out to be, which decides what's offered next: the household's product with this
 * barcode ("saved"), probably one it saved without its barcode ("likely"), a product it hasn't saved
 * ("new"), or something nothing recognized ("unknown")
 */
export type ScanOutcome = "saved" | "likely" | "new" | "unknown";

export function scanOutcome(scan: GroceryProductScan): ScanOutcome {
  if (scan.saved) return "saved";
  if (scan.likelySaved) return "likely";
  return scan.identified ? "new" : "unknown";
}

/** An ingredient picked from the list, or typed as a new one */
export type FoodChoice = { id: string; name: string } | string;

/** The ingredient's ID, adding it to the household's ingredients first when it's new */
export async function foodIdFor(api: ReturnType<typeof useUserApi>, foods: IngredientFood[], choice: FoodChoice): Promise<string> {
  if (typeof choice !== "string") return choice.id;
  const name = choice.trim();
  const existing = foods.find(food => food.name.toLowerCase() === name.toLowerCase());
  if (existing) return existing.id;
  const result = await api.groceries.createFood(name);
  if (!result.data) throw result.error;
  return result.data.id;
}

export function useGroceryScan() {
  const api = useUserApi();
  const { group } = useGroupSelf();
  const identifying = ref(false);
  const scan = ref<GroceryProductScan | null>(null);

  /** The household's AI can read a photo of a package, which a barcode nothing knew can fall back on */
  const canReadPhotos = computed(() => {
    const settings = group.value?.aiProviderSettings;
    if (!settings?.aiEnabled) return false;
    const task = settings.taskSettings?.find(setting => setting.task === "ingredient_parsing");
    return !!(settings.imageProviderEnabled || task?.imageProviderId);
  });

  /**
   * What a scanner result is. Its barcode is looked up first, which is fast and exact; its photo is read
   * by AI when the barcode didn't say, and keeps that barcode, so a product nothing knew still saves with it.
   */
  async function identify(result: ScannerResult): Promise<GroceryProductScan | null> {
    identifying.value = true;
    try {
      const previous = scan.value?.barcode && !scan.value.identified ? scan.value.barcode : null;
      let found: GroceryProductScan | null = null;
      if (result.barcode) {
        found = (await api.groceries.scanBarcode(result.barcode.text, result.barcode.format)).data;
      }
      if (result.photo && canReadPhotos.value && !found?.saved && !found?.identified) {
        const barcode = result.barcode ?? (previous ? { text: previous, format: null } : null);
        found = (await api.groceries.scanPhoto(result.photo, barcode)).data ?? found;
      }
      scan.value = found;
      return found;
    }
    finally {
      identifying.value = false;
    }
  }

  function reset() {
    scan.value = null;
  }

  return { identifying, scan, canReadPhotos, identify, reset };
}
