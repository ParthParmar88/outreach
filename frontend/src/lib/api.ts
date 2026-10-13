import type {
  Brief,
  BriefInput,
  FeedbackValue,
  ReplyDraft,
  RunResult,
  SearchPlan,
  SearchRun,
} from "./types";

/**
 * The backend, as far as the frontend is concerned.
 *
 * Follows the three objects in the repository README:
 *   Brief   → what the user filled in
 *   Plan    → compiled from a brief, frozen and hashed
 *   Run     → one execution of one plan
 *
 * The real client and the in-browser fake both implement this, so swapping
 * between them cannot break a screen.
 */
export interface Api {
  createBrief(input: BriefInput): Promise<Brief>;
  listBriefs(): Promise<Brief[]>;

  /** Compiles a brief into a frozen plan. This is where the one LLM call happens. */
  compilePlan(briefId: string): Promise<SearchPlan>;
  getPlan(planId: string): Promise<SearchPlan>;
  /** User edited the terms on the review screen, so recompile and rehash. */
  amendPlan(planId: string, terms: string[]): Promise<SearchPlan>;

  startRun(planId: string): Promise<SearchRun>;
  getRun(runId: string): Promise<SearchRun>;
  getRunResults(runId: string): Promise<RunResult[]>;

  sendFeedback(resultId: string, value: FeedbackValue): Promise<void>;
  draftReply(resultId: string, allowMention: boolean): Promise<ReplyDraft>;

  /** SSE endpoint. Empty string means this transport is unavailable. */
  runEventsUrl(runId: string): string;
  exportUrl(runId: string): string;
}

/** Empty by default, so the dev proxy in vite.config.ts handles it. */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* body was not json, keep the status line */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const httpApi: Api = {
  createBrief: (input) =>
    json("/api/v1/briefs", {
      method: "POST",
      body: JSON.stringify({
        product_name: input.productName,
        product_url: input.productUrl,
        description: input.description,
        keywords: input.keywords,
        sources: input.sources,
        days_back: input.daysBack,
      }),
    }),

  listBriefs: () => json("/api/v1/briefs"),

  compilePlan: (briefId) => json(`/api/v1/briefs/${briefId}/plan`, { method: "POST" }),

  getPlan: (planId) => json(`/api/v1/plans/${planId}`),

  amendPlan: (planId, terms) =>
    json(`/api/v1/plans/${planId}/amend`, {
      method: "POST",
      body: JSON.stringify({ terms }),
    }),

  startRun: (planId) => json(`/api/v1/plans/${planId}/runs`, { method: "POST" }),

  getRun: (runId) => json(`/api/v1/runs/${runId}`),

  getRunResults: (runId) => json(`/api/v1/runs/${runId}/results`),

  sendFeedback: (resultId, value) =>
    json(`/api/v1/results/${resultId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ useful: value === "useful" }),
    }),

  draftReply: (resultId, allowMention) =>
    json(`/api/v1/results/${resultId}/reply-draft`, {
      method: "POST",
      body: JSON.stringify({ allow_mention: allowMention }),
    }),

  runEventsUrl: (runId) => `${API_BASE}/api/v1/runs/${runId}/events`,

  exportUrl: (runId) => `${API_BASE}/api/v1/runs/${runId}/export.csv`,
};
