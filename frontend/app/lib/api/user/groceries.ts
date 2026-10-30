import { BaseAPI } from "../base/base-clients";
import type {
  GroceryCommonItemList, GroceryFoodRuleCreate, GroceryFoodRuleOut, GroceryItemAssignment, GroceryItemCheck,
  GroceryItemDelete, GroceryManualItemCreate, GroceryPhotoDraft, GroceryPhotoFindRequest, GroceryProductCreate, GroceryProductLookup,
  GroceryProductOut, GroceryProductPhotoAttach, GroceryProductScan,
  GroceryRestockBought, GroceryRestockCreate, GroceryRestockList,
  GrocerySuggestionOut, GroceryWeekGenerate, GroceryWeekView,
} from "~/lib/api/types/grocery";
import type { IngredientFood } from "~/lib/api/types/recipe";

const base = "/api/households/groceries";
const weekRoute = (week: string) => `${base}/weeks/${encodeURIComponent(week)}`;

export class GroceriesAPI extends BaseAPI {
  products() { return this.requests.get<GroceryProductOut[]>(`${base}/products`); }
  rules() { return this.requests.get<GroceryFoodRuleOut[]>(`${base}/rules`); }
  createProduct(data: GroceryProductCreate) { return this.requests.post<GroceryProductOut>(`${base}/products`, data); }
  updateProduct(id: string, data: GroceryProductCreate) { return this.requests.put<GroceryProductOut, GroceryProductCreate>(`${base}/products/${id}`, data); }
  deleteProduct(id: string) { return this.requests.delete(`${base}/products/${id}`); }
  /** What a product's store link says about it: its name, store, package size and ingredient */
  lookupProduct(url: string) { return this.requests.post<GroceryProductLookup>(`${base}/products/lookup`, { url }); }
  /** What a package's barcode is: the household's product with it, or the product as the barcode database knows it */
  scanBarcode(barcode: string, format?: string | null) {
    return this.requests.post<GroceryProductScan>(`${base}/products/scan/barcode`, { barcode, format: format ?? null });
  }

  /** What a photo of a package shows, read by AI, along with the barcode it showed if it did */
  scanPhoto(photo: Blob, barcode?: { text: string; format: string | null } | null) {
    const form = new FormData();
    form.append("image", photo, "package.jpg");
    if (barcode) {
      form.append("barcode", barcode.text);
      if (barcode.format) form.append("barcodeFormat", barcode.format);
    }
    return this.requests.post<GroceryProductScan>(`${base}/products/scan/photo`, form);
  }

  /** Keeps a photo someone took or picked for a product, as a draft to save with it */
  uploadPhoto(photo: Blob) {
    const form = new FormData();
    form.append("image", photo, "photo.jpg");
    return this.requests.post<GroceryPhotoDraft>(`${base}/photos`, form);
  }

  /** Looks for a product's photo: the store's for a store link, or Open Food Facts' for a barcode. Null when there's none. */
  findPhoto(where: GroceryPhotoFindRequest) { return this.requests.post<GroceryPhotoDraft | null>(`${base}/photos/find`, where); }
  /** Makes a draft photo the product's photo */
  attachPhoto(productId: string, token: string) {
    return this.requests.put<GroceryProductOut, GroceryProductPhotoAttach>(`${base}/products/${productId}/photo`, { token });
  }

  removePhoto(productId: string) { return this.requests.delete<GroceryProductOut>(`${base}/products/${productId}/photo`); }

  createRule(data: GroceryFoodRuleCreate) { return this.requests.post<GroceryFoodRuleOut>(`${base}/rules`, data); }
  updateRule(id: string, data: GroceryFoodRuleCreate) { return this.requests.put<GroceryFoodRuleOut, GroceryFoodRuleCreate>(`${base}/rules/${id}`, data); }
  deleteRule(id: string) { return this.requests.delete(`${base}/rules/${id}`); }
  createFood(name: string) { return this.requests.post<IngredientFood>("/api/foods", { name }); }
  week(week: string) { return this.requests.get<GroceryWeekView>(weekRoute(week)); }
  generate(week: string, data: GroceryWeekGenerate) { return this.requests.put<GroceryWeekView, GroceryWeekGenerate>(weekRoute(week), data); }
  assign(week: string, data: GroceryItemAssignment) { return this.requests.put<GroceryWeekView, GroceryItemAssignment>(`${weekRoute(week)}/assignment`, data); }
  check(week: string, data: GroceryItemCheck) { return this.requests.put<GroceryWeekView, GroceryItemCheck>(`${weekRoute(week)}/checked`, data); }
  addItem(week: string, data: GroceryManualItemCreate) { return this.requests.post<GroceryWeekView>(`${weekRoute(week)}/items`, data); }
  deleteItems(week: string, data: GroceryItemDelete) { return this.requests.post<GroceryWeekView>(`${weekRoute(week)}/items/delete`, data); }
  suggestions(date: string) { return this.requests.get<GrocerySuggestionOut[]>(`${base}/suggestions`, { plan_date: date }); }
  commonItems() { return this.requests.get<GroceryCommonItemList>(`${base}/common-items`); }
  restock() { return this.requests.get<GroceryRestockList>(`${base}/restock`); }
  addRestock(data: GroceryRestockCreate) { return this.requests.post<GroceryRestockList>(`${base}/restock`, data); }
  updateRestock(id: string, data: GroceryRestockCreate) { return this.requests.put<GroceryRestockList, GroceryRestockCreate>(`${base}/restock/${id}`, data); }
  removeRestock(id: string) { return this.requests.delete<GroceryRestockList>(`${base}/restock/${id}`); }
  setRestockBought(id: string, bought: boolean) { return this.requests.put<GroceryRestockList, GroceryRestockBought>(`${base}/restock/${id}/bought`, { bought }); }
}
