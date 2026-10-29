import { beforeEach, describe, expect, test, vi } from "vitest";
import type { GroceryProductScan } from "~/lib/api/types/grocery";
import { storeSearchUrl } from "../groceries/grocery-utils";
import { foodIdFor, scanOutcome, useGroceryScan } from "../groceries/use-grocery-scan";

const api = vi.hoisted(() => ({ scanBarcode: vi.fn(), scanPhoto: vi.fn(), createFood: vi.fn() }));
const settings = vi.hoisted(() => ({ value: { aiEnabled: true, imageProviderEnabled: true, taskSettings: [] as unknown[] } }));
vi.mock("~/composables/api", () => ({ useUserApi: () => ({ groceries: api }) }));
vi.mock("~/composables/use-groups", () => ({ useGroupSelf: () => ({ group: { value: { aiProviderSettings: settings.value } } }) }));

const draft = { name: "Great Value Whole Milk 1 gallon", store: "walmart" as const };
const product = { id: "p1", name: "Great Value Whole Milk, 1 gal" };

function scan(overrides: Partial<GroceryProductScan> = {}): GroceryProductScan {
  return { barcode: "0078742351865", identified: true, draft, saved: null, likelySaved: null, ...overrides } as GroceryProductScan;
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.value = { aiEnabled: true, imageProviderEnabled: true, taskSettings: [] };
});

describe("scanOutcome", () => {
  test("a saved product wins, then one that looks like it, then whether anything knew it", () => {
    expect(scanOutcome(scan({ saved: product as never, likelySaved: product as never }))).toBe("saved");
    expect(scanOutcome(scan({ likelySaved: product as never }))).toBe("likely");
    expect(scanOutcome(scan())).toBe("new");
    expect(scanOutcome(scan({ identified: false }))).toBe("unknown");
  });
});

describe("identify", () => {
  const photo = new Blob(["jpeg"], { type: "image/jpeg" });
  const barcode = { text: "078742351865", format: "UPC-A" };

  test("a barcode the database knows needs no photo", async () => {
    api.scanBarcode.mockResolvedValue({ data: scan() });
    const { identify } = useGroceryScan();

    const found = await identify({ barcode, photo });

    expect(api.scanBarcode).toHaveBeenCalledWith("078742351865", "UPC-A");
    expect(api.scanPhoto).not.toHaveBeenCalled();
    expect(found?.identified).toBe(true);
  });

  test("a barcode nothing knows has its photo read, along with the barcode", async () => {
    api.scanBarcode.mockResolvedValue({ data: scan({ identified: false, draft: { name: "" } as never }) });
    api.scanPhoto.mockResolvedValue({ data: scan({ draft: { name: "Kemps Whole Milk" } as never }) });
    const { identify } = useGroceryScan();

    const found = await identify({ barcode, photo });

    expect(api.scanPhoto).toHaveBeenCalledWith(photo, barcode);
    expect(found?.draft.name).toBe("Kemps Whole Milk");
  });

  test("the photo taken after an unknown barcode keeps that barcode", async () => {
    api.scanBarcode.mockResolvedValue({ data: scan({ identified: false, barcode: "0041483022011" }) });
    api.scanPhoto.mockResolvedValue({ data: scan() });
    const { identify } = useGroceryScan();

    await identify({ barcode: { text: "041483022011", format: null }, photo: null });
    await identify({ barcode: null, photo });

    expect(api.scanPhoto).toHaveBeenCalledWith(photo, { text: "0041483022011", format: null });
  });

  test("photos aren't sent without an AI that reads them", async () => {
    settings.value = { aiEnabled: true, imageProviderEnabled: false, taskSettings: [] };
    api.scanBarcode.mockResolvedValue({ data: scan({ identified: false }) });
    const { identify, canReadPhotos } = useGroceryScan();

    await identify({ barcode, photo });

    expect(canReadPhotos.value).toBe(false);
    expect(api.scanPhoto).not.toHaveBeenCalled();
  });

  test("an image provider chosen just for ingredient parsing reads photos too", () => {
    settings.value = { aiEnabled: true, imageProviderEnabled: false, taskSettings: [{ task: "ingredient_parsing", imageProviderId: "x" }] };
    expect(useGroceryScan().canReadPhotos.value).toBe(true);
  });
});

describe("foodIdFor", () => {
  const foods = [{ id: "f-milk", name: "milk" }] as never[];

  test("uses the household's ingredient, and adds a new one only when it's new", async () => {
    expect(await foodIdFor({ groceries: api } as never, foods, { id: "f-egg", name: "egg" })).toBe("f-egg");
    expect(await foodIdFor({ groceries: api } as never, foods, " Milk ")).toBe("f-milk");
    api.createFood.mockResolvedValue({ data: { id: "f-oat", name: "oat milk" } });
    expect(await foodIdFor({ groceries: api } as never, foods, "oat milk")).toBe("f-oat");
    expect(api.createFood).toHaveBeenCalledWith("oat milk");
  });
});

test("store searches find a product to copy its link from", () => {
  expect(storeSearchUrl("walmart", "Great Value Milk, 1 gal")).toBe("https://www.walmart.com/search?q=Great%20Value%20Milk%2C%201%20gal");
  expect(storeSearchUrl("whole_foods", "365 Milk")).toBe("https://www.wholefoodsmarket.com/search?text=365%20Milk");
});
