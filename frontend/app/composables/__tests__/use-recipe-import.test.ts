import { describe, expect, test } from "vitest";
import {
  findLinks,
  importFileKind,
  linkKey,
  linkSearchTerm,
  linkSource,
  planImport,
  progressStep,
  scraperError,
} from "../use-recipe-import";

const withAI = { ai: true, photos: true };
const withoutAI = { ai: false, photos: false };

function file(name: string, type = "") {
  return new File(["x"], name, { type });
}

describe("findLinks", () => {
  test("finds links in order, without repeats or the punctuation that ends a sentence", () => {
    expect(findLinks("Try https://a.test/one. Then (https://b.test/two), and https://a.test/one!")).toEqual([
      "https://a.test/one",
      "https://b.test/two",
    ]);
  });

  test("treats a bare www. link as https", () => {
    expect(findLinks("www.example.test/soup")).toEqual(["https://www.example.test/soup"]);
  });
});

describe("planImport", () => {
  test("an empty box has nothing to import", () => {
    expect(planImport("  \n ", [], withAI)).toMatchObject({ kind: "empty", blocker: null });
  });

  test("a link, even wrapped in a share sheet's line about it", () => {
    expect(planImport("https://example.test/soup", [], withAI)).toMatchObject({ kind: "link", url: "https://example.test/soup" });
    expect(planImport("Check out this reel by a chef I like! https://www.instagram.com/reel/ABC/", [], withAI))
      .toMatchObject({ kind: "link", url: "https://www.instagram.com/reel/ABC/" });
  });

  test("several links import together", () => {
    const plan = planImport("https://a.test/1\nhttps://b.test/2, https://c.test/3", [], withAI);
    expect(plan).toMatchObject({ kind: "links", urls: ["https://a.test/1", "https://b.test/2", "https://c.test/3"] });
  });

  test("a recipe that mentions its source is read as text, not imported from the link", () => {
    const recipe = [
      "Weeknight dal, adapted from https://example.test/dal",
      "1 cup red lentils, rinsed",
      "1 onion, diced",
      "2 cloves garlic",
      "1 tbsp curry powder",
      "Simmer the lentils with the onion, garlic and spices until soft, about 25 minutes.",
    ].join("\n");
    expect(planImport(recipe, [], withAI)).toMatchObject({ kind: "text", content: recipe, url: null });
  });

  test("HTML and JSON are read as markup, which needs no AI", () => {
    expect(planImport("<html><body>...</body></html>", [], withoutAI)).toMatchObject({ kind: "markup", blocker: null });
    expect(planImport("{\"@type\": \"Recipe\"}", [], withoutAI)).toMatchObject({ kind: "markup", blocker: null });
  });

  test("text and video posts need an AI provider; recipe sites don't", () => {
    expect(planImport("2 eggs, beaten", [], withoutAI)).toMatchObject({ kind: "text", blocker: "needs-ai" });
    expect(planImport("https://www.tiktok.com/@chef/video/123", [], withoutAI)).toMatchObject({ kind: "link", blocker: "needs-ai" });
    expect(planImport("https://example.test/soup", [], withoutAI)).toMatchObject({ kind: "link", blocker: null });
  });

  test("photos are read with any link or note that comes with them", () => {
    const photos = [file("a.jpg", "image/jpeg"), file("b.png", "image/png")];
    expect(planImport("https://example.test/soup", photos, withAI))
      .toMatchObject({ kind: "photos", photos, url: "https://example.test/soup", content: null, blocker: null });
    expect(planImport("Grandma's, from the blue binder", photos, withAI))
      .toMatchObject({ kind: "photos", url: null, content: "Grandma's, from the blue binder" });
  });

  test("photos need a provider that reads images", () => {
    const photos = [file("a.jpg", "image/jpeg")];
    expect(planImport("", photos, withoutAI).blocker).toBe("needs-ai");
    expect(planImport("", photos, { ai: true, photos: false }).blocker).toBe("needs-image-ai");
  });

  test("a cookbook or export is imported on its own", () => {
    const book = file("Salt Fat Acid Heat.epub");
    expect(planImport("", [book], withAI)).toMatchObject({ kind: "cookbook", file: book, blocker: null });
    expect(planImport("", [book], withoutAI)).toMatchObject({ kind: "cookbook", blocker: "needs-ai" });
    expect(planImport("", [book, file("a.jpg", "image/jpeg")], withAI)).toMatchObject({ kind: "cookbook", blocker: "one-file" });
    expect(planImport("", [file("export.zip", "application/zip")], withoutAI)).toMatchObject({ kind: "archive", blocker: null });
  });

  test("other files can't be imported", () => {
    expect(planImport("", [file("notes.docx")], withAI).blocker).toBe("unsupported-file");
  });
});

describe("importFileKind", () => {
  test("by type, or by name when the type is missing", () => {
    expect(importFileKind(file("x", "image/heic"))).toBe("photo");
    expect(importFileKind(file("IMG_0001.HEIC"))).toBe("photo");
    expect(importFileKind(file("book.pdf"))).toBe("cookbook");
    expect(importFileKind(file("x", "application/epub+zip"))).toBe("cookbook");
    expect(importFileKind(file("recipe.zip"))).toBe("archive");
    expect(importFileKind(file("notes.txt", "text/plain"))).toBe("other");
  });
});

describe("linkSource", () => {
  test("names video sites, and gives the host for anything else", () => {
    expect(linkSource("https://www.instagram.com/p/ABC/")).toEqual({ site: "Instagram", video: true });
    expect(linkSource("https://youtu.be/xyz")).toEqual({ site: "YouTube", video: true });
    expect(linkSource("https://m.facebook.com/watch?v=1")).toEqual({ site: "Facebook", video: true });
    expect(linkSource("https://www.seriouseats.com/chili")).toEqual({ site: "seriouseats.com", video: false });
    expect(linkSource("not a link")).toBeNull();
  });
});

describe("linkKey", () => {
  test("the same video matches however it was shared", () => {
    expect(linkKey("https://youtu.be/abc123?si=share")).toBe("youtube:abc123");
    expect(linkKey("https://www.youtube.com/watch?v=abc123&t=30")).toBe("youtube:abc123");
    expect(linkKey("https://m.youtube.com/shorts/abc123")).toBe("youtube:abc123");
    expect(linkKey("https://www.instagram.com/reel/C0de/?igsh=xyz")).toBe("instagram:C0de");
    expect(linkKey("https://instagram.com/chef/p/C0de")).toBe("instagram:C0de");
    expect(linkKey("https://www.tiktok.com/@chef/video/42?is_from_webapp=1")).toBe("tiktok:42");
  });

  test("pages match without tracking parameters or a trailing slash, but keep the ones that pick a recipe", () => {
    expect(linkKey("https://www.example.test/chili/?utm_source=x&fbclid=y")).toBe("example.test/chili");
    expect(linkKey("https://example.test/chili")).toBe("example.test/chili");
    expect(linkKey("https://example.test/recipe.php?id=12&ref=home")).toBe("example.test/recipe.php?id=12");
    expect(linkKey("https://example.test/recipe.php?id=13")).not.toBe(linkKey("https://example.test/recipe.php?id=12"));
  });
});

describe("linkSearchTerm", () => {
  test("searches by a video's ID, or a page's host and path", () => {
    expect(linkSearchTerm("https://youtu.be/abc123")).toBe("abc123");
    expect(linkSearchTerm("https://www.example.test/chili/?utm_source=x")).toBe("example.test/chili");
    expect(linkSearchTerm("https://example.test/recipe.php?id=12")).toBe("example.test/recipe.php");
  });

  test("skips terms too short to be worth searching", () => {
    expect(linkSearchTerm("https://youtu.be/ab")).toBeNull();
    expect(linkSearchTerm("nope")).toBeNull();
  });
});

describe("messages", () => {
  test("the scraper's error codes are recognized", () => {
    expect(scraperError("BAD_RECIPE_DATA")).toBe("no-recipe");
    expect(scraperError("CONNECTION_ERROR")).toBe("unreachable");
    expect(scraperError("This post doesn't include the recipe in its caption.")).toBeNull();
    expect(scraperError(undefined)).toBeNull();
  });

  test("progress steps lose their trailing ellipsis", () => {
    expect(progressStep("Fetching webpage...")).toBe("Fetching webpage");
    expect(progressStep("Reading video…")).toBe("Reading video");
  });
});
