import type { ReaderOptions } from "zxing-wasm/reader";

/**
 * Reading the barcodes on grocery packages, from camera frames as the scanner looks and from photos.
 *
 * Safari has no barcode reader of its own (no BarcodeDetector), so this uses ZXing compiled to
 * WebAssembly. It's loaded the first time the scanner opens, and served by Mealie itself rather than
 * the CDN it would otherwise come from. Where the browser has a reader, as Chrome on Android does, that
 * one is used instead: it's faster.
 */

export interface ScannedBarcode {
  /** The digits, as the scanner read them */
  text: string;
  /** The format the scanner read, e.g. "UPC-E", which tells it from an EAN-8 */
  format: string | null;
}

/** The barcodes printed on grocery packages */
const ZXING_FORMATS: ReaderOptions["formats"] = ["EAN13", "EAN8", "UPCA", "UPCE"];
const NATIVE_FORMATS: Record<string, string> = { ean_13: "EAN-13", ean_8: "EAN-8", upc_a: "UPC-A", upc_e: "UPC-E" };

interface NativeBarcodeDetector {
  detect(source: ImageBitmapSource): Promise<{ rawValue: string; format: string }[]>;
}
interface NativeBarcodeDetectorClass {
  new (options: { formats: string[] }): NativeBarcodeDetector;
  getSupportedFormats(): Promise<string[]>;
}

/** Whether some text is a package barcode's digits: 8, or 12 to 14, ignoring spaces */
export function looksLikeBarcode(text: string): boolean {
  return /^(\d{8}|\d{12,14})$/.test(text.replace(/[\s-]/g, ""));
}

let native: Promise<NativeBarcodeDetector | null> | null = null;

function nativeDetector(): Promise<NativeBarcodeDetector | null> {
  native ??= (async () => {
    const Detector = (globalThis as { BarcodeDetector?: NativeBarcodeDetectorClass }).BarcodeDetector;
    if (!Detector) return null;
    try {
      const supported = await Detector.getSupportedFormats();
      const formats = Object.keys(NATIVE_FORMATS).filter(format => supported.includes(format));
      return formats.length ? new Detector({ formats }) : null;
    }
    catch {
      return null;
    }
  })();
  return native;
}

type ZXingReader = typeof import("zxing-wasm/reader");
let zxing: Promise<ZXingReader> | null = null;

function loadZxing(): Promise<ZXingReader> {
  zxing ??= (async () => {
    const [reader, wasm] = await Promise.all([
      import("zxing-wasm/reader"),
      import("zxing-wasm/reader/zxing_reader.wasm?url"),
    ]);
    await reader.prepareZXingModule({
      overrides: {
        locateFile: (path: string, prefix: string) => (path.endsWith(".wasm") ? wasm.default : prefix + path),
      },
      fireImmediately: true,
    });
    return reader;
  })();
  // a failed load can be tried again next time
  zxing.catch(() => (zxing = null));
  return zxing;
}

/** Starts loading the reader, so it's ready by the time a barcode comes into view */
export function preloadBarcodeReader(): void {
  void nativeDetector().then(detector => (detector ? undefined : loadZxing().catch(() => undefined)));
}

/** The barcode in an image, or null when there isn't one that reads */
export async function readBarcode(image: ImageData | Blob): Promise<ScannedBarcode | null> {
  const detector = await nativeDetector();
  if (detector) {
    try {
      const [found] = await detector.detect(image);
      if (found?.rawValue) {
        return { text: found.rawValue, format: NATIVE_FORMATS[found.format] ?? null };
      }
      return null;
    }
    catch {
      // fall through to ZXing, which reads anything the browser's reader can't open
    }
  }

  const { readBarcodes } = await loadZxing();
  const results = await readBarcodes(image, {
    formats: ZXING_FORMATS,
    tryHarder: true,
    tryRotate: true,
    maxNumberOfSymbols: 1,
  });
  const found = results.find(result => result.isValid && result.text);
  return found ? { text: found.text, format: found.format || null } : null;
}

/**
 * A photo, decoded and upright. Older Safari turns down the orientation option, and older still has no
 * createImageBitmap for files, so each is tried in turn; images drawn from an <img> come out upright.
 */
async function decodePhoto(photo: Blob): Promise<{ image: CanvasImageSource; width: number; height: number; done: () => void } | null> {
  for (const options of [{ imageOrientation: "from-image" } as ImageBitmapOptions, undefined]) {
    try {
      const bitmap = await createImageBitmap(photo, options);
      return { image: bitmap, width: bitmap.width, height: bitmap.height, done: () => bitmap.close() };
    }
    catch {
      // try the next way
    }
  }
  const url = URL.createObjectURL(photo);
  try {
    const element = new Image();
    element.src = url;
    await element.decode();
    return { image: element, width: element.naturalWidth, height: element.naturalHeight, done: () => URL.revokeObjectURL(url) };
  }
  catch {
    URL.revokeObjectURL(url);
    return null;
  }
}

/** A photo drawn at no more than `maxSide` pixels a side, as pixels and on a canvas */
async function drawImage(photo: Blob, maxSide: number): Promise<{ pixels: ImageData; canvas: HTMLCanvasElement } | null> {
  const decoded = await decodePhoto(photo);
  if (!decoded) return null;
  try {
    const scale = Math.min(1, maxSide / Math.max(decoded.width, decoded.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(decoded.width * scale));
    canvas.height = Math.max(1, Math.round(decoded.height * scale));
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return null;
    // on white, as a JPEG would show any transparency in it
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(decoded.image, 0, 0, canvas.width, canvas.height);
    return { pixels: context.getImageData(0, 0, canvas.width, canvas.height), canvas };
  }
  finally {
    decoded.done();
  }
}

function toJpeg(canvas: HTMLCanvasElement, quality = 0.85): Promise<Blob | null> {
  return new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
}

/**
 * A photo ready to send: no more than 1600 pixels a side, so it uploads quickly from a phone, along with
 * any barcode it shows (read at a larger size, where small barcodes still have enough detail).
 */
export async function preparePhoto(photo: Blob): Promise<{ photo: Blob; barcode: ScannedBarcode | null }> {
  const large = await drawImage(photo, 2400);
  const barcode = large ? await readBarcode(large.pixels).catch(() => null) : null;
  return { photo: await shrinkPhoto(photo), barcode };
}

/** A photo no more than 1600 pixels a side, as a JPEG, so it uploads quickly from a phone */
export async function shrinkPhoto(photo: Blob): Promise<Blob> {
  const small = await drawImage(photo, 1600);
  return (small ? await toJpeg(small.canvas) : null) ?? photo;
}
