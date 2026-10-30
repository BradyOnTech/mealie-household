/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type GroceryStore = "walmart" | "cub" | "aldi" | "whole_foods";
export type GroceryUnit =
  "count" | "gram" | "kilogram" | "ounce" | "pound" | "milliliter" | "liter" | "fluid_ounce" | "cup";
export type GroceryPhotoSource = "store" | "open_food_facts" | "scan" | "chosen";
export type GroceryRuleKind = "pantry" | "recurring";
export type GroceryRecurringMode = "minimum" | "extra";
export type GroceryRestockStatus = "waiting" | "listed" | "bought";
export type PlanEntryType = "breakfast" | "lunch" | "dinner" | "side" | "snack" | "drink" | "dessert";

export interface GroceryBarcodeScanRequest {
  barcode: string;
  format?: string | null;
}
export interface GroceryCommonItemList {
  items?: GroceryCommonItemOut[];
  nextListWeek?: string | null;
  stores?: GroceryStore[];
}
export interface GroceryCommonItemOut {
  food: IngredientFoodSummary;
  aisle?: string | null;
  products: GroceryProductOut[];
  listed?: boolean;
}
export interface IngredientFoodSummary {
  id: string;
  name: string;
  pluralName?: string | null;
}
export interface GroceryProductOut {
  foodId: string;
  name: string;
  store: GroceryStore;
  url?: string | null;
  priority?: number;
  enabled?: boolean;
  packageQuantity?: number | null;
  packageUnit?: GroceryUnit | null;
  notes?: string;
  barcode?: string | null;
  groupId: string;
  householdId: string;
  id: string;
  food: IngredientFoodSummary;
  photo?: string | null;
  photoSource?: GroceryPhotoSource | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface GroceryFoodRuleCreate {
  foodId: string;
  kind: GroceryRuleKind;
  quantity: number;
  unit: GroceryUnit;
  mode?: GroceryRecurringMode;
  enabled?: boolean;
}
export interface GroceryFoodRuleOut {
  foodId: string;
  kind: GroceryRuleKind;
  quantity: number;
  unit: GroceryUnit;
  mode?: GroceryRecurringMode;
  enabled?: boolean;
  groupId: string;
  householdId: string;
  id: string;
  food: IngredientFoodSummary;
}
export interface GroceryFoodRuleSave {
  foodId: string;
  kind: GroceryRuleKind;
  quantity: number;
  unit: GroceryUnit;
  mode?: GroceryRecurringMode;
  enabled?: boolean;
  groupId: string;
  householdId: string;
}
export interface GroceryItemAssignment {
  itemIds: [string, ...string[]];
  store?: GroceryStore | null;
  productId?: string | null;
  expectedRevision: number;
}
export interface GroceryItemCheck {
  itemIds: [string, ...string[]];
  checked: boolean;
  expectedRevision: number;
}
export interface GroceryItemDelete {
  itemIds: [string, ...string[]];
  expectedRevision: number;
}
export interface GroceryManualItemCreate {
  foodId?: string | null;
  note?: string;
  quantity?: number;
  unit?: GroceryUnit;
  store?: GroceryStore | null;
  expectedRevision: number;
}
export interface GroceryPhotoDraft {
  token: string;
  source: GroceryPhotoSource;
}
export interface GroceryPhotoFindRequest {
  url?: string | null;
  barcode?: string | null;
}
export interface GroceryProductCreate {
  foodId: string;
  name: string;
  store: GroceryStore;
  url?: string | null;
  priority?: number;
  enabled?: boolean;
  packageQuantity?: number | null;
  packageUnit?: GroceryUnit | null;
  notes?: string;
  barcode?: string | null;
}
export interface GroceryProductLookup {
  url?: string | null;
  barcode?: string | null;
  name?: string;
  store?: GroceryStore | null;
  packageQuantity?: number | null;
  packageUnit?: GroceryUnit | null;
  food?: IngredientFoodSummary | null;
  newFoodName?: string | null;
  readWithAi?: boolean;
  photo?: GroceryPhotoDraft | null;
}
export interface GroceryProductLookupRequest {
  url: string;
}
export interface GroceryProductPhotoAttach {
  token: string;
}
export interface GroceryProductSave {
  foodId: string;
  name: string;
  store: GroceryStore;
  url?: string | null;
  priority?: number;
  enabled?: boolean;
  packageQuantity?: number | null;
  packageUnit?: GroceryUnit | null;
  notes?: string;
  barcode?: string | null;
  groupId: string;
  householdId: string;
}
export interface GroceryProductScan {
  barcode?: string | null;
  identified?: boolean;
  draft: GroceryProductLookup;
  saved?: GroceryProductOut | null;
  likelySaved?: GroceryProductOut | null;
}
export interface GroceryPurchaseOut {
  key: string;
  foodName: string;
  store: GroceryStore | null;
  product: GroceryProductOut | null;
  items: ShoppingListItemOut[];
  packageCount?: number | null;
  packageQuantityNeeded?: number | null;
  quantityNote?: string;
}
export interface ShoppingListItemOut {
  quantity?: number;
  unit?: IngredientUnit | null;
  food?: IngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  shoppingListId: string;
  checked?: boolean;
  position?: number;
  foodId?: string | null;
  labelId?: string | null;
  unitId?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  id: string;
  groupId: string;
  householdId: string;
  label?: MultiPurposeLabelSummary | null;
  recipeReferences?: ShoppingListItemRecipeRefOut[];
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientUnit {
  id: string;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  fraction?: boolean;
  abbreviation?: string;
  pluralAbbreviation?: string | null;
  useAbbreviation?: boolean;
  aliases?: IngredientUnitAlias[];
  standardQuantity?: number | null;
  standardUnit?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientUnitAlias {
  name: string;
}
export interface IngredientFood {
  id: string;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  labelId?: string | null;
  aliases?: IngredientFoodAlias[];
  substitutions?: IngredientFoodSubstitution[];
  householdsWithIngredientFood?: string[];
  label?: MultiPurposeLabelSummary | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface IngredientFoodAlias {
  name: string;
}
export interface IngredientFoodSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
  substituteFood?: IngredientFoodSummary | null;
}
export interface MultiPurposeLabelSummary {
  name: string;
  color?: string;
  groupId: string;
  id: string;
}
export interface Recipe {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  lastMade?: string | null;
  recipeIngredient?: RecipeIngredient[];
  recipeInstructions?: RecipeStep[] | null;
  nutrition?: Nutrition | null;
  settings?: RecipeSettings | null;
  assets?: RecipeAsset[] | null;
  notes?: RecipeNote[] | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  comments?: RecipeCommentOut[] | null;
}
export interface RecipeCategory {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTag {
  id?: string | null;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
}
export interface RecipeTool {
  id: string;
  groupId?: string | null;
  name: string;
  slug: string;
  recipeCount?: number;
  householdsWithTool?: string[];
}
export interface RecipeIngredient {
  quantity?: number | null;
  unit?: IngredientUnit | CreateIngredientUnit | null;
  food?: IngredientFood | CreateIngredientFood | null;
  referencedRecipe?: Recipe | null;
  note?: string | null;
  display?: string;
  title?: string | null;
  originalText?: string | null;
  substitutions?: RecipeIngredientSubstitution[];
  referenceId?: string;
}
export interface CreateIngredientUnit {
  id?: string | null;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  fraction?: boolean;
  abbreviation?: string;
  pluralAbbreviation?: string | null;
  useAbbreviation?: boolean;
  aliases?: CreateIngredientUnitAlias[];
  standardQuantity?: number | null;
  standardUnit?: string | null;
}
export interface CreateIngredientUnitAlias {
  name: string;
}
export interface CreateIngredientFood {
  id?: string | null;
  name: string;
  pluralName?: string | null;
  description?: string;
  extras?: {
    [k: string]: unknown;
  } | null;
  labelId?: string | null;
  aliases?: CreateIngredientFoodAlias[];
  substitutions?: CreateIngredientFoodSubstitution[];
  householdsWithIngredientFood?: string[];
}
export interface CreateIngredientFoodAlias {
  name: string;
}
export interface CreateIngredientFoodSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
}
export interface RecipeIngredientSubstitution {
  substituteFoodId?: string | null;
  note?: string | null;
  substituteFood?: IngredientFoodSummary | null;
}
export interface RecipeStep {
  id?: string | null;
  title?: string | null;
  summary?: string | null;
  text: string;
  ingredientReferences?: IngredientReferences[];
  noteReferences?: NoteReference[];
}
export interface IngredientReferences {
  referenceId?: string | null;
}
export interface NoteReference {
  referenceId?: string | null;
}
export interface Nutrition {
  calories?: string | null;
  carbohydrateContent?: string | null;
  cholesterolContent?: string | null;
  fatContent?: string | null;
  fiberContent?: string | null;
  proteinContent?: string | null;
  saturatedFatContent?: string | null;
  sodiumContent?: string | null;
  sugarContent?: string | null;
  transFatContent?: string | null;
  unsaturatedFatContent?: string | null;
}
export interface RecipeSettings {
  public?: boolean;
  showNutrition?: boolean;
  showAssets?: boolean;
  landscapeView?: boolean;
  disableComments?: boolean;
  locked?: boolean;
}
export interface RecipeAsset {
  name: string;
  icon: string;
  fileName?: string | null;
}
export interface RecipeNote {
  title: string;
  text: string;
  referenceId?: string;
}
export interface RecipeCommentOut {
  id: string;
  recipeId: string;
  text: string;
  createdAt: string;
  updatedAt: string;
  userId: string;
  user: UserBase;
}
export interface UserBase {
  id: string;
  username?: string | null;
  admin: boolean;
  fullName?: string | null;
}
export interface ShoppingListItemRecipeRefOut {
  recipeId: string;
  recipeQuantity?: number;
  recipeScale?: number | null;
  recipeNote?: string | null;
  id: string;
  shoppingListItemId: string;
}
export interface GroceryRestockBought {
  bought?: boolean;
}
export interface GroceryRestockCreate {
  name: string;
  foodId?: string | null;
  quantity?: number | null;
  unit?: GroceryUnit | null;
  store?: GroceryStore | null;
  note?: string;
}
export interface GroceryRestockList {
  items?: GroceryRestockOut[];
  recentlyBought?: GroceryRestockOut[];
  nextListWeek?: string | null;
}
export interface GroceryRestockOut {
  name: string;
  foodId?: string | null;
  quantity?: number | null;
  unit?: GroceryUnit | null;
  store?: GroceryStore | null;
  note?: string;
  id: string;
  groupId: string;
  householdId: string;
  food?: IngredientFoodSummary | null;
  addedBy?: string;
  shoppingListItemId?: string | null;
  weekStart?: string | null;
  boughtAt?: string | null;
  status?: GroceryRestockStatus;
  createdAt?: string | null;
  updatedAt?: string | null;
}
export interface GroceryStorePage {
  url: string;
  photo?: GroceryPhotoDraft | null;
}
export interface GroceryStorePageRequest {
  barcode: string;
  store: GroceryStore;
  name?: string;
}
export interface GrocerySuggestionOut {
  recipe: RecipeSummary;
  score: number;
  reasons: string[];
}
export interface RecipeSummary {
  id?: string | null;
  userId?: string;
  householdId?: string;
  groupId?: string;
  name?: string | null;
  slug?: string;
  image?: unknown;
  recipeServings?: number;
  recipeYieldQuantity?: number;
  recipeYield?: string | null;
  totalTime?: string | null;
  prepTime?: string | null;
  cookTime?: string | null;
  performTime?: string | null;
  description?: string | null;
  recipeCategory?: RecipeCategory[] | null;
  tags?: RecipeTag[] | null;
  tools?: RecipeTool[];
  rating?: number | null;
  orgURL?: string | null;
  dateAdded?: string | null;
  dateUpdated?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  lastMade?: string | null;
}
export interface GroceryWeekGenerate {
  stores:
    | [GroceryStore]
    | [GroceryStore, GroceryStore]
    | [GroceryStore, GroceryStore, GroceryStore]
    | [GroceryStore, GroceryStore, GroceryStore, GroceryStore];
  mealScales?: {
    [k: string]: number;
  };
  skipOnHand?: boolean;
  expectedRevision?: number;
}
export interface GroceryWeekOut {
  id: string;
  groupId: string;
  householdId: string;
  weekStart: string;
  shoppingListId: string;
  stores: GroceryStore[];
  mealScales: {
    [k: string]: number;
  };
  revision: number;
  skipOnHand: boolean;
  warnings?: string[];
}
export interface GroceryWeekView {
  weekStart: string;
  week?: GroceryWeekOut | null;
  shoppingList?: ShoppingListOut | null;
  meals?: ReadPlanEntry[];
  purchases?: GroceryPurchaseOut[];
  warnings?: string[];
}
export interface ShoppingListOut {
  name?: string | null;
  extras?: {
    [k: string]: unknown;
  } | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  groupId: string;
  userId: string;
  id: string;
  listItems?: ShoppingListItemOut[];
  householdId: string;
  recipeReferences?: ShoppingListRecipeRefOut[];
  labelSettings?: ShoppingListMultiPurposeLabelOut[];
}
export interface ShoppingListRecipeRefOut {
  id: string;
  shoppingListId: string;
  recipeId: string;
  recipeQuantity: number;
  recipe: RecipeSummary;
}
export interface ShoppingListMultiPurposeLabelOut {
  shoppingListId: string;
  labelId: string;
  position?: number;
  id: string;
  label: MultiPurposeLabelSummary;
}
export interface ReadPlanEntry {
  date: string;
  entryType?: PlanEntryType;
  title?: string;
  text?: string;
  recipeId?: string | null;
  id: number;
  groupId: string;
  userId: string;
  householdId: string;
  recipe?: RecipeSummary | null;
}
