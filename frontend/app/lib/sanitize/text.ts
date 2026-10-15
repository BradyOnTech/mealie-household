/**
 * Truncates plain text to `length` characters, appending `clamp` when truncated.
 *
 * The input is treated strictly as text and is never parsed as HTML, so markup in the input is
 * returned verbatim rather than interpreted.
 */
export function truncateText(text: string, length = 20, clamp = "..."): string {
  return text.length > length ? text.slice(0, length) + clamp : text;
}

/**
 * Reduces markdown (or stray HTML) to one line of plain text for previews, cut at a word boundary
 * near `length`. Markup is stripped with patterns, never parsed, and the result is meant to be
 * rendered as text.
 */
export function plainTextExcerpt(markdown: string, length = 140, clamp = "…"): string {
  const text = markdown
    .replace(/<[^>]*>/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_~`#>|]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= length) {
    return text;
  }
  const cut = text.slice(0, length);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > length * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}${clamp}`;
}
