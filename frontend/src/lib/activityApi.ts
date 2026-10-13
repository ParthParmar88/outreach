/* ------------------------------------------------------------------ *
 * One question, one call: what has outreach done for me?
 *
 * Account-wide, not per product. Someone wants to know whether the tool is
 * worth the time, and that answer does not live inside any single product.
 * ------------------------------------------------------------------ */

import { ApiError } from "./productApi";

export interface PlatformActivity {
  key: string;
  name: string;
  /** False means we cannot search it yet. Shown anyway, with the reason. */
  connected: boolean;
  searches: number;
  results: number;
  written: number;
  posted: number;
  answered: number;
  skipped: number;
}

export interface ActivityTotals {
  searches: number;
  results: number;
  written: number;
  posted: number;
  answered: number;
  skipped: number;
}

export interface Activity {
  products: number;
  /** Which product these numbers are about. Null means every product. */
  product: { id: string; name: string; domain: string } | null;
  totals: ActivityTotals;
  platforms: PlatformActivity[];
  /** Only present for replies somebody actually judged. Often empty. */
  outcomes: Partial<Record<"ignored" | "conversation" | "lead" | "customer", number>>;
}

export const activityApi = {
  /** Pass a product id for one product's numbers, or nothing for all of them. */
  async get(productId?: string): Promise<Activity> {
    const query = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
    let response: Response;
    try {
      response = await fetch(`/api/v1/activity${query}`, { credentials: "include" });
    } catch {
      throw new ApiError(
        "Cannot reach the backend. Start it with: uvicorn outreach.main:app --reload",
        0,
      );
    }
    if (!response.ok) {
      if (response.status === 401) {
        window.dispatchEvent(new Event("outreach:unauthorised"));
      }
      throw new ApiError(`${response.status} ${response.statusText}`, response.status);
    }
    return (await response.json()) as Activity;
  },
};
