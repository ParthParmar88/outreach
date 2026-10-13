/* ------------------------------------------------------------------ *
 * PLACEHOLDER.
 *
 * The real version of this file is generated from the backend OpenAPI
 * schema and must not be edited by hand:
 *
 *     npm run types
 *
 * That command does not work yet because the FastAPI service does not
 * answer. Until it does, these types are written by hand and act as the
 * frontend's half of the contract. When the backend lands, run the
 * generator and delete everything below this comment that it replaces.
 * ------------------------------------------------------------------ */

export type SourceId = "github" | "hackernews" | "reddit";

export interface SourceOption {
  id: SourceId;
  label: string;
  disabled?: boolean;
  reason?: string;
}

/* ================================================================== *
 * 1. Brief — what the user filled in. Mutable, human facing.
 * ================================================================== */

export type DaysBack = 7 | 30 | 90;

export interface BriefInput {
  productName: string;
  productUrl: string;
  description: string;
  keywords: string[];
  sources: SourceId[];
  daysBack: DaysBack;
}

export interface Brief extends BriefInput {
  id: string;
  createdAt: string;
  latestPlanId?: string;
  latestRunId?: string;
  latestRunState?: RunState;
  resultCount?: number;
}

/* ================================================================== *
 * 2. SearchPlan — compiled from a Brief. Frozen, versioned, hashed.
 *    The only thing the pipeline ever executes.
 * ================================================================== */

export interface PlanTerm {
  term: string;
  /** "user" = they typed it. "expansion" = the one LLM call added it. */
  origin: "user" | "expansion";
  /** Required for expansion terms. The user has to be able to judge it. */
  reason?: string;
}

/**
 * Predicates are what the user DECLARED. They become SQL WHERE clauses
 * before any scoring happens. Never mixed with score components.
 */
export interface PlanPredicates {
  sources: SourceId[];
  dateFrom: string;
  dateTo: string;
  language: string;
  minEngagement: number;
  excludedTerms: string[];
}

export interface ExamplePost {
  source: SourceId;
  title: string;
  body: string;
}

export interface SearchPlan {
  id: string;
  briefId: string;
  /** Content hash. Two identical plans have the same hash and the same cost. */
  planHash: string;
  version: number;
  terms: PlanTerm[];
  predicates: PlanPredicates;
  stages: StageId[];
  estimatedDocuments: number;
  estimatedCostUsd: number;
  /** Written out in full. Anyone can judge an example; nobody can judge a plan. */
  examplePosts: ExamplePost[];
}

/* ================================================================== *
 * 3. SearchRun — one execution of one plan. A durable row.
 * ================================================================== */

export type StageId =
  | "expand"
  | "coverage"
  | "fetch"
  | "normalize"
  | "dedupe"
  | "embed"
  | "retrieve"
  | "fuse"
  | "rerank"
  | "analyze"
  | "score"
  | "diversify"
  | "synthesize"
  | "persist";

export type RunState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface StageProgress {
  id: StageId;
  label: string;
  state: "waiting" | "running" | "done" | "skipped";
  /** "2,014 → 1,186" */
  detail?: string;
}

export interface SearchRun {
  id: string;
  planId: string;
  state: RunState;
  stages: StageProgress[];
  percent: number;
  costUsd: number;
  callsUsed: number;
  callBudget: number;
  error?: string;
}

/* ================================================================== *
 * Results
 * ================================================================== */

export type Band = "very-high" | "high" | "medium" | "weak";

export interface ScoreComponent {
  name: string;
  /** 0 to 1, what the model inferred. */
  raw: number;
  weight: number;
  /** raw * weight * 100 */
  points: number;
}

export interface ScoreDetail {
  components: ScoreComponent[];
  /** 0 to 1. MULTIPLIES the subtotal. It is not a sixth component. */
  relevance: number;
  subtotal: number;
  final: number;
}

export type FeedbackValue = "useful" | "not-useful";

export interface Conversation {
  source: SourceId;
  url: string;
  title: string;
  author: string;
  createdAt: string;
  engagement: string;
}

export interface RunResult {
  id: string;
  rank: number;
  score: number;
  band: Band;
  conversation: Conversation;
  problem: string;
  activelyLooking: boolean;
  /** 1 to 5 */
  painSeverity: number;
  /** 0 to 1 */
  productFit: number;
  /** Verified to exist in the source text before it is ever stored. */
  evidenceQuote: string;
  scoreDetail: ScoreDetail;
  feedback?: FeedbackValue;
}

export interface ReplyDraft {
  text: string;
  mentionsProduct: boolean;
}

/* ================================================================== *
 * Helpers
 * ================================================================== */

export function bandOf(score: number): Band {
  if (score >= 75) return "very-high";
  if (score >= 55) return "high";
  if (score >= 32) return "medium";
  return "weak";
}

export const BAND_LABEL: Record<Band, string> = {
  "very-high": "Very high",
  high: "High",
  medium: "Medium",
  weak: "Weak",
};
