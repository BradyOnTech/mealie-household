import { describe, expect, it } from "vitest";
import { detectGroceryStore, mondayFor } from "../grocery-utils";

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
