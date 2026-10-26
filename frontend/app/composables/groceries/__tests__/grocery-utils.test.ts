import { describe, expect, it } from "vitest";
import { commonItemAisles, commonItemStore, detectGroceryStore, groceryError, mondayFor } from "../grocery-utils";
import type { CommonItemAisle } from "../grocery-utils";
import type { GroceryCommonItemOut, GroceryProductOut, GroceryStore } from "~/lib/api/types/grocery";

function product(food: string, store: GroceryStore, name: string): GroceryProductOut {
  return { id: `${food}-${store}`, foodId: food, name, store, groupId: "group", householdId: "household", food: { id: food, name: food } };
}

function common(name: string, aisle: string | null, products: GroceryProductOut[]): GroceryCommonItemOut {
  return { food: { id: name, name }, aisle, products, listed: false };
}

function names(aisles: CommonItemAisle[]) {
  return aisles.flatMap(aisle => aisle.rows.map(row => row.item.food.name));
}

describe("common items", () => {
  const items = [
    common("Bananas", "Produce", [product("Bananas", "aldi", "Bananas")]),
    common("Jalapeño", "Produce", [product("Jalapeño", "walmart", "Fresh jalapeño peppers")]),
    common("Milk", "Dairy", [product("Milk", "walmart", "Great Value 2% milk"), product("Milk", "aldi", "Friendly Farms 2% milk")]),
    common("Paper towels", null, [product("Paper towels", "walmart", "Bounty Select-a-Size")]),
  ];

  it("groups by aisle, with unlabeled ingredients last, and shows the product the list would buy", () => {
    const aisles = commonItemAisles(items, null, "");
    expect(aisles.map(aisle => aisle.name)).toEqual(["Dairy", "Produce", ""]);
    expect(names(aisles)).toEqual(["Milk", "Bananas", "Jalapeño", "Paper towels"]);
    expect(aisles[0]?.rows[0]?.product.name).toBe("Great Value 2% milk");
  });

  it("shows only what the chosen store sells, with that store's product", () => {
    const rows = commonItemAisles(items, "aldi", "").flatMap(aisle => aisle.rows);
    expect(rows.map(row => `${row.item.food.name}: ${row.product.name}`)).toEqual(["Milk: Friendly Farms 2% milk", "Bananas: Bananas"]);
  });

  it("matches every word of a search, ignoring case and accents", () => {
    expect(names(commonItemAisles(items, null, "2% MILK"))).toEqual(["Milk"]);
    expect(names(commonItemAisles(items, null, "jalapeno"))).toEqual(["Jalapeño"]);
    expect(names(commonItemAisles(items, null, "  bounty "))).toEqual(["Paper towels"]);
    expect(commonItemAisles(items, null, "milk bananas")).toEqual([]);
  });

  it("searches only the products at the chosen store", () => {
    expect(names(commonItemAisles(items, "walmart", "great value"))).toEqual(["Milk"]);
    expect(commonItemAisles(items, "aldi", "great value")).toEqual([]);
  });

  it("buys an added item where its row showed it", () => {
    const [milk] = commonItemAisles(items, null, "milk").flatMap(aisle => aisle.rows);
    if (!milk) throw new Error("Milk is a common item");
    // On the trip, the list picks; off it, the row's store is pinned so the item doesn't go unassigned
    expect(commonItemStore(milk, null, ["walmart", "aldi"])).toBeNull();
    expect(commonItemStore(milk, null, ["aldi"])).toBe("walmart");
    // Browsing one store's items means buying there
    expect(commonItemStore(milk, "aldi", ["walmart", "aldi"])).toBe("aldi");
    // With no list yet, the next list picks when it's made
    expect(commonItemStore(milk, null, [])).toBeNull();
  });
});

describe("grocery product links", () => {
  it("recognizes retailer domains and subdomains", () => {
    expect(detectGroceryStore("https://www.walmart.com/ip/product/123")).toBe("walmart");
    expect(detectGroceryStore("https://shop.cub.com/store/cub/products/123")).toBe("cub");
    expect(detectGroceryStore("https://www.aldi.us/product/123")).toBe("aldi");
    expect(detectGroceryStore("https://www.wholefoodsmarket.com/product/123")).toBe("whole_foods");
  });
  it("does not infer a retailer from a lookalike host or unrelated URL", () => {
    expect(detectGroceryStore("https://walmart.com.example.org/ip/123")).toBeNull();
    expect(detectGroceryStore("https://example.org/?store=walmart.com")).toBeNull();
    expect(detectGroceryStore("not a URL")).toBeNull();
  });
});

describe("calendar week selection", () => {
  it("keeps Monday and maps Sunday back to the same week", () => {
    expect(mondayFor("2026-10-12")).toBe("2026-10-12");
    expect(mondayFor("2026-10-18")).toBe("2026-10-12");
    expect(mondayFor("2027-01-01")).toBe("2026-12-28");
  });
});

describe("request errors", () => {
  it("shows the server's message, whatever shape it comes in", () => {
    expect(groceryError({ response: { data: { detail: "Product not found" } } })).toBe("Product not found");
    expect(groceryError({ response: { data: { detail: [{ msg: "Name what you're out of" }] } } })).toBe("Name what you're out of");
    expect(groceryError({ response: { data: { detail: { message: "Set up an AI provider", error: true } } } })).toBe("Set up an AI provider");
    expect(groceryError({ message: "Network Error" })).toBe("Network Error");
  });
});
