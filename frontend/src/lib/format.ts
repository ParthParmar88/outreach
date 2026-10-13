import type { SourceId } from "./types";

export const SOURCE_LABEL: Record<SourceId, string> = {
  github: "GitHub",
  hackernews: "Hacker News",
  reddit: "Reddit",
};

export function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 31) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.round(days / 30);
  return `${months} month${months === 1 ? "" : "s"} ago`;
}

export function money(usd: number): string {
  return usd < 0.01 ? "<$0.01" : `$${usd.toFixed(2)}`;
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** "run_8f3a2c" → "8f3a2c" for display next to a hash. */
export function shortHash(hash: string): string {
  return hash.replace(/^[a-z]+_/, "").slice(0, 8);
}
