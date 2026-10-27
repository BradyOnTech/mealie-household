import { describe, expect, test, vi } from "vitest";
import { applicationServerKey, isAppleMobile } from "../use-web-push";

vi.mock("~/composables/api", () => ({ useUserApi: () => ({ messages: {} }) }));

describe("applicationServerKey", () => {
  test("decodes base64url without padding", () => {
    // 0xfb 0xff 0xbf encodes to "-_-_" in base64url, which plain base64 would reject
    expect(Array.from(applicationServerKey("-_-_"))).toEqual([0xFB, 0xFF, 0xBF]);
    expect(Array.from(applicationServerKey("AQI"))).toEqual([1, 2]);
  });

  test("decodes a VAPID public key to an uncompressed P-256 point", () => {
    const key = "BOVaZWfqdKUQjO2ViKgi5VGfi4SGBMRgjfwa1rDrZ0IKGqlEmYrSvOCqzYlnJNEmjcFBgSBTwFNvbmxdHEelKmo";
    const bytes = applicationServerKey(key);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(0x04);
  });
});

describe("isAppleMobile", () => {
  function device(userAgent: string, platform: string, maxTouchPoints: number) {
    vi.stubGlobal("navigator", { userAgent, platform, maxTouchPoints });
  }

  test("knows an iPhone, and an iPad asking for the desktop site", () => {
    device("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone", 5);
    expect(isAppleMobile()).toBe(true);

    device("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 5);
    expect(isAppleMobile()).toBe(true);

    device("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "MacIntel", 0);
    expect(isAppleMobile()).toBe(false);

    vi.unstubAllGlobals();
  });
});
