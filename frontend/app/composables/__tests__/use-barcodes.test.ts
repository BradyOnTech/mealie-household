import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const zxing = vi.hoisted(() => ({ readBarcodes: vi.fn(), prepareZXingModule: vi.fn() }));
vi.mock("zxing-wasm/reader", () => zxing);
vi.mock("zxing-wasm/reader/zxing_reader.wasm?url", () => ({ default: "/_nuxt/zxing_reader.wasm" }));

async function freshModule() {
  vi.resetModules();
  return await import("../groceries/use-barcodes");
}

const frame = { width: 1, height: 1, data: new Uint8ClampedArray(4) } as unknown as ImageData;

beforeEach(() => {
  vi.clearAllMocks();
  zxing.prepareZXingModule.mockResolvedValue({});
});

afterEach(() => {
  delete (globalThis as { BarcodeDetector?: unknown }).BarcodeDetector;
});

describe("looksLikeBarcode", () => {
  test.each([
    ["078742351865", true],
    ["0 78742 35186 5", true],
    ["0078742351865", true],
    ["04252614", true],
    ["12345", false],
    ["0787423518651234", false],
    ["milk", false],
  ])("%s → %s", async (text, expected) => {
    const { looksLikeBarcode } = await freshModule();
    expect(looksLikeBarcode(text)).toBe(expected);
  });
});

describe("readBarcode", () => {
  test("ZXing reads grocery barcodes, from Mealie's own copy of its WebAssembly", async () => {
    zxing.readBarcodes.mockResolvedValue([{ isValid: true, text: "078742351865", format: "UPC-A" }]);
    const { readBarcode } = await freshModule();

    expect(await readBarcode(frame)).toEqual({ text: "078742351865", format: "UPC-A" });

    const options = zxing.readBarcodes.mock.calls[0]![1];
    expect(options.formats).toEqual(["EAN13", "EAN8", "UPCA", "UPCE"]);
    const { locateFile } = zxing.prepareZXingModule.mock.calls[0]![0].overrides;
    expect(locateFile("zxing_reader.wasm", "https://cdn.example/")).toBe("/_nuxt/zxing_reader.wasm");
  });

  test("an unreadable frame has no barcode", async () => {
    zxing.readBarcodes.mockResolvedValue([{ isValid: false, text: "", format: "" }]);
    const { readBarcode } = await freshModule();
    expect(await readBarcode(frame)).toBeNull();
  });

  test("the browser's own reader is used where there is one", async () => {
    const detect = vi.fn().mockResolvedValue([{ rawValue: "04252614", format: "upc_e" }]);
    const created: unknown[] = [];
    class FakeBarcodeDetector {
      static getSupportedFormats = vi.fn().mockResolvedValue(["ean_13", "upc_a", "upc_e", "qr_code"]);
      detect = detect;
      constructor(options: unknown) {
        created.push(options);
      }
    }
    (globalThis as { BarcodeDetector?: unknown }).BarcodeDetector = FakeBarcodeDetector;
    const { readBarcode } = await freshModule();

    expect(await readBarcode(frame)).toEqual({ text: "04252614", format: "UPC-E" });
    expect(created).toEqual([{ formats: ["ean_13", "upc_a", "upc_e"] }]);
    expect(zxing.readBarcodes).not.toHaveBeenCalled();
  });
});
