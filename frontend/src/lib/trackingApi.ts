/* ------------------------------------------------------------------ *
 * The reply funnel: draft a reply, say you posted it, say what it was
 * worth.
 *
 * Nothing here posts anything to GitHub, and nothing ever will. You copy
 * the draft and reply yourself; "I posted it" is you telling us, which is
 * the only reason we can later say who replied to whom.
 * ------------------------------------------------------------------ */

import { ApiError } from "./productApi";

export type TrackState = "drafted" | "posted" | "answered" | "skipped";
export type Outcome = "ignored" | "conversation" | "lead" | "customer";

export interface TrackedPost {
  id: string;
  source: string;
  source_id: string;
  url: string;
  title: string | null;
  author: string | null;
  container: string | null;
  kind: string;
  score_when_found: number;

  state: TrackState;

  draft: string | null;
  draft_mentions_product: boolean;
  drafted_at: string | null;
  /** Non-empty means: do not reply to this, and here is why. */
  skip_reason: string | null;

  posted_at: string | null;
  our_comment_url: string | null;
  replies_after: number;
  author_replied: boolean;
  last_checked_at: string | null;

  outcome: Outcome | null;
  outcome_note: string | null;
}

export interface Funnel {
  drafted: number;
  posted: number;
  answered: number;
  skipped: number;
}

export interface TrackingBoard {
  funnel: Funnel;
  posts: TrackedPost[];
}

/** What the results screen knows about a post when you press Draft a reply. */
export interface DraftRequest {
  /** The platform the post is on: the run's `platform`, e.g. "hackernews".
      Activity counts replies per platform by this. */
  source: string;
  source_id: string;
  url: string;
  title: string;
  body: string;
  author: string;
  container: string;
  kind: string;
  score: number;
  run_id?: string | null;
  allow_mention: boolean;
}

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      ...init,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the backend. Start it with: uvicorn outreach.main:app --reload",
      0,
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      // A 422 from FastAPI is a list of field errors, not a string. Showing
      // "[object Object]" to somebody is worse than showing the status.
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not json, keep the status line */
    }
    if (response.status === 401) {
      window.dispatchEvent(new Event("outreach:unauthorised"));
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const trackingApi = {
  /**
   * Write a reply to one post and start tracking it.
   *
   * Slow on purpose — 5 to 15 seconds, and no background job. You are
   * looking at the post waiting for the words, so polling would add
   * machinery and no benefit.
   */
  async draft(productId: string, post: DraftRequest): Promise<TrackedPost> {
    return request<TrackedPost>(`/products/${productId}/tracking/draft`, {
      method: "POST",
      body: JSON.stringify(post),
    });
  },

  /**
   * Look at posted replies' threads again and mark the answered ones.
   *
   * For one product, or the whole account without one. Each post is fetched
   * at most every few minutes however often this is called, so a screen
   * can call it every time it opens. `changed` says the numbers on screen
   * are now out of date.
   */
  async checkReplies(productId?: string): Promise<{ checked: number; changed: number }> {
    const query = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
    return request(`/tracking/check-replies${query}`, { method: "POST" });
  },

  async board(productId: string): Promise<TrackingBoard> {
    return request<TrackingBoard>(`/products/${productId}/tracking`);
  },

  async markPosted(
    trackedId: string,
    commentUrl: string | null,
    threadComments = 0,
  ): Promise<TrackedPost> {
    return request<TrackedPost>(`/tracking/${trackedId}/posted`, {
      method: "POST",
      body: JSON.stringify({
        comment_url: commentUrl || null,
        thread_comments: threadComments,
      }),
    });
  },

  async setOutcome(
    trackedId: string,
    outcome: Outcome,
    note?: string,
  ): Promise<TrackedPost> {
    return request<TrackedPost>(`/tracking/${trackedId}/outcome`, {
      method: "POST",
      body: JSON.stringify({ outcome, note: note || null }),
    });
  },

  async skip(trackedId: string, reason: string): Promise<TrackedPost> {
    return request<TrackedPost>(`/tracking/${trackedId}/skip`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },
};
