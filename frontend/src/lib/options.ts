import type { SourceOption } from "./types";

/* ================================================================== *
 * Form configuration. Real, not sample data.
 *
 * Extracted from mockData.ts when the fake backend was deleted - these
 * are choices the brief form offers, and have nothing to do with mocking.
 * ================================================================== */

export const SOURCE_OPTIONS: SourceOption[] = [
  { id: "github", label: "GitHub issues" },
  {
    id: "hackernews",
    label: "Hacker News",
    disabled: true,
    reason: "Connector not built yet",
  },
  {
    id: "reddit",
    label: "Reddit",
    disabled: true,
    reason: "Commercial use of their data requires an agreement",
  },
];

export const DATE_OPTIONS = [
  { value: 7, label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
] as const;

/**
 * Keywords are NOT listed here any more.
 *
 * A checked-in list is correct for exactly one product and quietly wrong for
 * every other one — and worse, it looks helpful while pointing the search
 * somewhere the user never asked about. Suggestions now come from
 * POST /api/v1/keywords/suggest, derived from the description they typed.
 */
