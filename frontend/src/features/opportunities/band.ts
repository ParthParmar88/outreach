import type { Opportunity } from "@/lib/productApi";

/**
 * How strong a lead looks, as a colour.
 *
 * Shared rather than declared next to each screen that shows a score: the
 * home page and the results page showing the same number in two different
 * colours would be worse than either choice on its own.
 */
export const BAND_COLOR: Record<Opportunity["band"], "error" | "warning" | "info" | "default"> = {
  "very-high": "error",
  high: "warning",
  medium: "info",
  weak: "default",
};

/** Matches `score.MEDIUM` on the backend. Below this is the collapsed pile. */
export const WEAK_BELOW = 20;

/**
 * A platform key as somebody would write it.
 *
 * The key is what the backend and the URL carry, and it is not a name:
 * printing it raw put "Opportunities on hackernews" at the top of a page.
 * Shared rather than repeated, because three screens showing the same
 * platform under three spellings is worse than any one of them.
 */
const PLATFORM_NAME: Record<string, string> = {
  github: "GitHub",
  hackernews: "Hacker News",
};

export function platformName(key: string): string {
  return PLATFORM_NAME[key] ?? key;
}
