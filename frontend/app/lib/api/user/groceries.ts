import { BaseAPI } from "../base/base-clients";
import type {
  GroceryFoodRuleCreate, GroceryFoodRuleOut, GroceryItemAssignment, GroceryItemCheck,
  GroceryItemDelete, GroceryManualItemCreate, GroceryProductCreate, GroceryProductOut,
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
}
