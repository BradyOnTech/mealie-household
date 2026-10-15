import { describe, expect, test, vi } from "vitest";
import { plainTextExcerpt, truncateText } from "./text";

describe("truncateText", () => {
  test("returns short text unchanged", () => {
    expect(truncateText("Dinner")).toEqual("Dinner");
  });

  test("truncates long text with clamp", () => {
    expect(truncateText("a".repeat(25))).toEqual(`${"a".repeat(20)}...`);
  });

  test("respects custom length and clamp", () => {
    expect(truncateText("abcdef", 3, "~")).toEqual("abc~");
  });

  test("does not clamp text exactly at the length boundary", () => {
    expect(truncateText("abcde", 5)).toEqual("abcde");
    expect(truncateText("abcdef", 5)).toEqual("abcde...");
  });

  // Markup in the input must be treated as plain text and never parsed into the live document.
  test("does not parse or execute HTML payloads", () => {
    const createElement = vi.spyOn(document, "createElement");
    const payload = "<img src=x onerror=alert(1)>";

    const result = truncateText(payload);

    // The payload is returned verbatim (truncated only by length), proving it is treated as text.
    expect(result).toEqual(`${payload.slice(0, 20)}...`);
    // No DOM element is constructed, so no <img> can fire its onerror handler.
    expect(createElement).not.toHaveBeenCalled();
    createElement.mockRestore();
  });
});

describe("plainTextExcerpt", () => {
  test("returns plain text unchanged", () => {
    expect(plainTextExcerpt("Seared salmon in a curry sauce.")).toEqual("Seared salmon in a curry sauce.");
  });

  test("strips markdown emphasis, links, images and headings", () => {
    expect(plainTextExcerpt("## Quick **weeknight** [dinner](https://example.com) ![photo](x.jpg)"))
      .toEqual("Quick weeknight dinner photo");
  });

  test("collapses line breaks into single spaces", () => {
    expect(plainTextExcerpt("First line\n\nSecond   line")).toEqual("First line Second line");
  });

  test("cuts long text at a word boundary", () => {
    expect(plainTextExcerpt("one two three four five six", 15)).toEqual("one two three…");
  });

  test("removes tags without parsing them into the document", () => {
    const createElement = vi.spyOn(document, "createElement");

    expect(plainTextExcerpt("<img src=x onerror=alert(1)>Soup")).toEqual("Soup");
    expect(createElement).not.toHaveBeenCalled();
    createElement.mockRestore();
  });
});
