/* ------------------------------------------------------------------ *
 * PLACEHOLDER. The real version is generated from the backend schema.
 *
 * Field metadata lives apart from the form component so that when the
 * backend starts publishing it, only this file is replaced.
 * ------------------------------------------------------------------ */

import { DATE_OPTIONS, SOURCE_OPTIONS } from "@/lib/options";

export { DATE_OPTIONS, SOURCE_OPTIONS };

export const FIELD_COPY = {
  productName: {
    label: "Product name",
    placeholder: "Acme",
    help: " ",
  },
  productUrl: {
    label: "Product website",
    placeholder: "https://example.com",
    help: "We read this once to learn what you sell.",
  },
  description: {
    label: "What are you looking for?",
    placeholder:
      "Developers whose search index goes stale after their documents change",
    help: "Plain English. This is what finds the person who described the same problem in completely different words.",
  },
  keywords: {
    label: "Keywords",
    placeholder: "Type a word and press Enter",
    help: "One to three words each — they are matched as exact phrases, so a whole sentence finds nothing. Suggestions appear once you have described what you are looking for.",
  },
  sources: {
    label: "Where to search",
    help: "More sources are added over time.",
  },
  daysBack: {
    label: "How far back",
    help: "A live thread beats a dead one.",
  },
} as const;

export const VALIDATION_COPY = {
  productName: "Give the product a name.",
  productUrl: "Include the full address, starting with https://",
  description:
    "Write at least one full sentence. This is the field that finds posts using different words.",
  keywords: "Add at least one keyword.",
  sources: "Choose at least one place to search.",
} as const;

/**
 * Why the description has a real minimum: keywords alone turn the product
 * into a word matcher, and it will miss the person who wrote "my bill
 * exploded because I resend the whole document history every time".
 */
export const DESCRIPTION_MIN = 25;
