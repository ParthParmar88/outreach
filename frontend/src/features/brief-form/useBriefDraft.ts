import { useCallback, useEffect, useRef } from "react";

import type { BriefInput } from "@/lib/types";

const STORAGE_KEY = "outreach.brief.draft.v2";

/**
 * A genuinely empty brief.
 *
 * This used to arrive pre-filled with a sample product and its keywords, which made
 * every new search start as a search for someone else's product. Placeholders
 * belong in `fields.ts`; values belong to the user.
 */
export const EMPTY_BRIEF: BriefInput = {
  productName: "",
  productUrl: "",
  description: "",
  keywords: [],
  sources: ["github"],
  daysBack: 30,
};

/**
 * Keeps the half-filled brief in localStorage.
 *
 * A brief takes a minute of real thought to write. Losing it to an
 * accidental refresh is the kind of small betrayal people do not forgive,
 * and this costs twelve lines to prevent.
 */
export function useBriefDraft() {
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback((): BriefInput => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return EMPTY_BRIEF;
      return { ...EMPTY_BRIEF, ...(JSON.parse(raw) as Partial<BriefInput>) };
    } catch {
      return EMPTY_BRIEF;
    }
  }, []);

  /** Debounced so typing does not hit storage on every keystroke. */
  const save = useCallback((values: Partial<BriefInput>) => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
      } catch {
        /* private mode, or storage full. Not worth interrupting anyone over. */
      }
    }, 400);
  }, []);

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* nothing to do */
    }
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return { load, save, clear };
}
