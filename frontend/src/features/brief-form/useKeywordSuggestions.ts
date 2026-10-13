import { useEffect, useRef, useState } from "react";

import { API_BASE } from "@/lib/api";

/**
 * Keyword suggestions for whatever the user has described so far.
 *
 * The form used to ship a checked-in list, which was right for one product
 * and quietly wrong for every other. These come from the description
 * instead, so the suggestions are about what this person is actually
 * looking for.
 *
 * Debounced hard: every call costs a model request, and someone typing a
 * sentence should produce one, not forty.
 */
export function useKeywordSuggestions(description: string) {
  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);

    if (description.trim().length < 25) {
      setOptions([]);
      return;
    }

    // Aborted on the next keystroke, so a slow response cannot overwrite a
    // newer one.
    const controller = new AbortController();

    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/v1/keywords/suggest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description }),
          signal: controller.signal,
        });
        setOptions(res.ok ? ((await res.json()) as string[]) : []);
      } catch {
        // An autocomplete that fails should offer nothing, not break the
        // form someone is halfway through filling in.
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }, 900);

    return () => {
      window.clearTimeout(timer.current);
      controller.abort();
    };
  }, [description]);

  return { options, loading };
}
