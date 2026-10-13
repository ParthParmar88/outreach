import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/client";
import { subscribe, type SseHandle } from "@/lib/sse";
import type { RunResult, SearchRun } from "@/lib/types";

const POLL_MS = 900;

interface State {
  run: SearchRun | null;
  results: RunResult[];
  error: string | null;
  transport: "sse" | "polling";
}

/**
 * Subscribes to one run.
 *
 * Tries SSE first, falls back to polling if the stream fails twice or the
 * transport is unavailable. Either way the caller gets the same three
 * things, so no screen has to know which one is in use.
 *
 * Results are refetched alongside the status so they appear as they land,
 * rather than all at once when the run finishes.
 */
export function useRunStream(runId: string | undefined) {
  const [state, setState] = useState<State>({
    run: null,
    results: [],
    error: null,
    transport: "sse",
  });

  const sse = useRef<SseHandle | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    const pull = async () => {
      try {
        const [run, results] = await Promise.all([
          api.getRun(runId),
          api.getRunResults(runId),
        ]);
        if (cancelled) return;
        setState((s) => ({ ...s, run, results, error: null }));
        return run;
      } catch (err) {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            error: err instanceof Error ? err.message : "Unknown error.",
          }));
        }
        return undefined;
      }
    };

    const poll = async () => {
      const run = await pull();
      if (cancelled) return;
      if (!run || run.state === "running" || run.state === "queued") {
        timer.current = window.setTimeout(poll, POLL_MS);
      }
    };

    const startPolling = () => {
      setState((s) => ({ ...s, transport: "polling" }));
      void poll();
    };

    const url = api.runEventsUrl(runId);
    if (!url) {
      startPolling();
    } else {
      void pull(); // paint immediately, do not wait for the first frame
      sse.current = subscribe<SearchRun>({
        url,
        onMessage: (run) => {
          if (cancelled) return;
          setState((s) => ({ ...s, run, error: null }));
          void api
            .getRunResults(runId)
            .then((results) => !cancelled && setState((s) => ({ ...s, results })))
            .catch(() => {
              /* the next frame will retry */
            });
        },
        onGiveUp: () => {
          if (!cancelled) startPolling();
        },
      });
    }

    return () => {
      cancelled = true;
      sse.current?.close();
      sse.current = null;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [runId]);

  return state;
}
