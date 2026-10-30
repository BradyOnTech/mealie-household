import { afterEach, describe, expect, it, vi } from "vitest";
import { useStaticRoutes } from "../static-routes";

function routes(subPath = "") {
  vi.stubGlobal("useNuxtApp", () => ({ $config: { public: { SUB_PATH: subPath } } }));
  return useStaticRoutes();
}

describe("grocery product photos", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("addresses a product's photo by its version, so a new photo has a new address", () => {
    const { groceryProductPhoto } = routes();
    expect(groceryProductPhoto({ id: "p1", photo: "a1b2c3d4" })).toBe("/api/households/groceries/products/p1/photo/thumb?v=a1b2c3d4");
    expect(groceryProductPhoto({ id: "p1", photo: "e5f6a7b8" }, "photo")).toBe("/api/households/groceries/products/p1/photo/photo?v=e5f6a7b8");
  });

  it("has no address for a product without a photo", () => {
    expect(routes().groceryProductPhoto({ id: "p1", photo: null })).toBeNull();
  });

  it("addresses a draft photo by its token, under Mealie's sub-path", () => {
    expect(routes().groceryDraftPhoto("0123abcd".repeat(4))).toBe(`/api/households/groceries/photos/${"0123abcd".repeat(4)}/thumb`);
    expect(routes("/mealie").groceryDraftPhoto("ab".repeat(16), "photo")).toBe(`/mealie/api/households/groceries/photos/${"ab".repeat(16)}/photo`);
  });
});
