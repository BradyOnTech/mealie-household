/**
 * The import box takes whatever someone has for a recipe: a link or several, the recipe's text or
 * markup, photos, a cookbook, or a Mealie export. `planImport` works out which importer reads it, so
 * nobody has to pick one, and these helpers describe links and spot ones that were imported before.
 */

/** What was handed to the import box, and so which importer reads it */
export type ImportKind
  = | "empty"
  /** One link, to a recipe site or a video post */
    | "link"
  /** Several links, imported together in the background */
    | "links"
  /** A page's HTML, or schema.org Recipe JSON, read like a web page */
    | "markup"
  /** The recipe's text, read with AI */
    | "text"
  /** Photos or screenshots of one recipe, read with AI along with any text or link */
    | "photos"
  /** A PDF or EPUB cookbook, imported in the background */
    | "cookbook"
  /** A recipe exported from Mealie as a .zip */
    | "archive";

/** Why the import box can't import what it was given */
export type ImportBlocker
  /** Text, photos, a cookbook or a video post, and no AI provider */
  = | "needs-ai"
  /** Photos, and no AI provider that reads images */
    | "needs-image-ai"
  /** A cookbook or export alongside other files: these are imported on their own */
    | "one-file"
  /** A file none of the importers read */
    | "unsupported-file";

export interface ImportPlan {
  kind: ImportKind;
  blocker: ImportBlocker | null;
  /** The link to import, or for text and photos, the recipe's source */
  url: string | null;
  /** Several links, for `links` */
  urls: string[];
  /** The recipe's text or markup, or for photos, any notes to read with them */
  content: string | null;
  photos: File[];
  /** The cookbook or export */
  file: File | null;
}

export interface ImportAbilities {
  /** The group has an AI provider */
  ai: boolean;
  /** The group has an AI provider that can read photos of a recipe */
  photos: boolean;
}

export type ImportFileKind = "photo" | "cookbook" | "archive" | "other";

/** File types the import box takes, for file pickers */
export const IMPORT_FILE_TYPES = {
  photo: "image/*",
  cookbook: "application/pdf,.pdf,application/epub+zip,.epub",
  archive: ".zip,application/zip",
} as const;

export function importFileKind(file: File): ImportFileKind {
  const name = file.name.toLowerCase();
  if (file.type.startsWith("image/") || /\.(jpe?g|png|webp|gif|heic|heif|avif)$/.test(name)) {
    return "photo";
  }
  if (["application/pdf", "application/epub+zip"].includes(file.type) || /\.(pdf|epub)$/.test(name)) {
    return "cookbook";
  }
  if (file.type.includes("zip") || name.endsWith(".zip")) {
    return "archive";
  }
  return "other";
}

// A link starts with a scheme or www., and ends at whitespace or a character that can't be in one
const LINK = /\b(?:https?:\/\/|www\.)[^\s<>"'`]+/gi;
// Punctuation that ends a sentence rather than the link in it
const TRAILING_PUNCTUATION = /[.,;:!?)\]}'"]+$/;
/**
 * How much other text may come with each link and still count as just links: share sheets wrap a
 * link in a line about it ("Check out this reel by @chef!"), while a recipe with its source link
 * runs to hundreds of characters.
 */
const SHARE_TEXT_PER_LINK = 80;

/** The links in some text, in order and without repeats, minus any punctuation that ends a sentence */
export function findLinks(text: string): string[] {
  const links = Array.from(text.matchAll(LINK), (match) => {
    const link = match[0].replace(TRAILING_PUNCTUATION, "");
    return /^www\./i.test(link) ? `https://${link}` : link;
  });
  return [...new Set(links)];
}

const VIDEO_SITES: [RegExp, string][] = [
  [/(^|\.)instagram\.com$/, "Instagram"],
  [/(^|\.)tiktok\.com$/, "TikTok"],
  [/(^|\.)(youtube\.com|youtu\.be)$/, "YouTube"],
  [/(^|\.)(facebook\.com|fb\.watch)$/, "Facebook"],
  [/(^|\.)vimeo\.com$/, "Vimeo"],
  [/(^|\.)dailymotion\.com$/, "Dailymotion"],
];

export interface LinkSource {
  /** The site's name for video sites, otherwise its host, e.g. "Instagram" or "seriouseats.com" */
  site: string;
  /** A post where the video is the recipe, read from its caption and captions with AI */
  video: boolean;
}

export function linkSource(url: string): LinkSource | null {
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase().replace(/^(www|m)\./, "");
  }
  catch {
    return null;
  }
  const video = VIDEO_SITES.find(([pattern]) => pattern.test(host));
  return { site: video ? video[1] : host, video: !!video };
}

export function planImport(text: string, files: File[], can: ImportAbilities): ImportPlan {
  const plan: ImportPlan = { kind: "empty", blocker: null, url: null, urls: [], content: null, photos: [], file: null };
  const trimmed = text.trim();
  const kinds = files.map(importFileKind);

  if (kinds.includes("other")) {
    return { ...plan, blocker: "unsupported-file" };
  }

  const fileKind = kinds.find(kind => kind === "cookbook" || kind === "archive");
  if (fileKind) {
    const file = files[kinds.indexOf(fileKind)] ?? null;
    let blocker: ImportBlocker | null = null;
    if (files.length > 1) {
      blocker = "one-file";
    }
    else if (fileKind === "cookbook" && !can.ai) {
      blocker = "needs-ai";
    }
    return { ...plan, kind: fileKind, file, blocker };
  }

  const links = findLinks(trimmed);
  const otherText = trimmed.replace(LINK, " ").replace(/\s+/g, " ").trim();
  const justLinks = links.length > 0 && otherText.length <= SHARE_TEXT_PER_LINK * links.length;

  if (files.length) {
    const url = justLinks && links.length === 1 ? links[0]! : null;
    let blocker: ImportBlocker | null = null;
    if (!can.ai) {
      blocker = "needs-ai";
    }
    else if (!can.photos) {
      blocker = "needs-image-ai";
    }
    return { ...plan, kind: "photos", photos: files, url, content: url ? null : trimmed || null, blocker };
  }

  if (!trimmed) {
    return plan;
  }

  if (justLinks) {
    if (links.length > 1) {
      return { ...plan, kind: "links", urls: links };
    }
    const url = links[0]!;
    return { ...plan, kind: "link", url, blocker: !can.ai && linkSource(url)?.video ? "needs-ai" : null };
  }

  if (/^[<{[]/.test(trimmed)) {
    return { ...plan, kind: "markup", content: trimmed };
  }

  return { ...plan, kind: "text", content: trimmed, blocker: can.ai ? null : "needs-ai" };
}

// Query parameters that track where a link was shared, rather than say which recipe it is
const TRACKING_PARAM = /^(utm_.*|fbclid|gclid|igsh|igshid|si|feature|ref|ref_src|share.*|mc_.*|_.*)$/i;

/**
 * What a link points to, so the same recipe matches however it was shared: video posts by their
 * ID, and pages by host, path and any query that isn't tracking.
 */
export function linkKey(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  }
  catch {
    return null;
  }

  const host = parsed.hostname.toLowerCase().replace(/^(www|m)\./, "");
  const path = parsed.pathname.replace(/\/+$/, "");
  const segments = path.split("/").filter(Boolean);
  const after = (...names: string[]) => {
    const at = segments.findIndex(segment => names.includes(segment.toLowerCase()));
    return at >= 0 ? segments[at + 1] : undefined;
  };

  let id: string | null | undefined;
  if (host === "youtu.be") {
    id = segments[0];
  }
  else if (/(^|\.)youtube\.com$/.test(host)) {
    id = parsed.searchParams.get("v") || after("shorts", "embed", "live");
  }
  else if (/(^|\.)instagram\.com$/.test(host)) {
    id = after("p", "reel", "reels", "tv");
  }
  else if (/(^|\.)tiktok\.com$/.test(host)) {
    id = after("video");
  }
  if (id) {
    const site = linkSource(url)!.site.toLowerCase();
    return `${site}:${id}`;
  }

  const query = [...parsed.searchParams.entries()]
    .filter(([name]) => !TRACKING_PARAM.test(name))
    .sort(([a], [b]) => a.localeCompare(b));
  const search = query.length ? `?${new URLSearchParams(query).toString()}` : "";
  return `${host}${path}${search}`;
}

/**
 * The part of a link to look for among saved recipes' sources: a video's ID, or a page's path.
 * Matches are confirmed with `linkKey`, since a search this loose finds near misses too.
 */
export function linkSearchTerm(url: string): string | null {
  const key = linkKey(url);
  if (!key) {
    return null;
  }

  const term = key.includes(":") && !key.includes("/") ? key.slice(key.indexOf(":") + 1) : key.replace(/\?.*$/, "");
  // quotes would end the search's string; anything shorter than this matches too much to be useful
  return term.length >= 4 && !term.includes("\"") ? term : null;
}

/** The scraper's error codes, which the link and markup importers report as their message */
const SCRAPER_ERRORS: Record<string, "no-recipe" | "unreachable"> = {
  BAD_RECIPE_DATA: "no-recipe",
  NO_RECIPE_DATA: "no-recipe",
  CONNECTION_ERROR: "unreachable",
};

/** Whether an import's error message is one of the scraper's codes, and which */
export function scraperError(message: string | null | undefined): "no-recipe" | "unreachable" | null {
  return (message && SCRAPER_ERRORS[message.trim()]) || null;
}

/** A progress message without the trailing ellipsis, for a list of steps */
export function progressStep(message: string): string {
  return message.trim().replace(/(\.\.\.|…)$/, "");
}
