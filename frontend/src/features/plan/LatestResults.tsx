/* ------------------------------------------------------------------ *
 * The last GitHub search, summarised, next to the plan that produced it.
 *
 * The plan and its results used to be two screens with nothing joining
 * them, which made a genuine question hard to answer: did editing the plan
 * change what came back? You had to remember the old numbers.
 *
 * So this is a summary, not the results screen. A few leads and a count,
 * enough to see whether the last change helped; the full list stays on its
 * own page, because twenty cards under a plan is a page nobody scrolls.
 *
 * The search button here is independent of the plan's Rewrite button on
 * purpose. Re-planning and re-searching answer different questions — "are
 * we looking for the right thing" and "has anything new been posted" — and
 * tying them together means you cannot ask the second without paying for
 * the first.
 * ------------------------------------------------------------------ */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import HistoryIcon from "@mui/icons-material/HistoryToggleOff";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";

import { IconTile, Label, Surface, hairline } from "@/components/ui";
import { BAND_COLOR, platformName } from "@/features/opportunities/band";
import { productApi, type Opportunity, type OpportunityRun } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

/** Enough to tell whether the last change helped. The rest is a click away. */
const PREVIEW = 4;

interface Props {
  productId: string;
  /** Every source that can be searched today, in plan order. */
  platforms: string[];
  /** Start a fresh search on one platform. The plan screen owns navigation. */
  onSearch: (platform: string) => void;
}

export default function LatestResults({ productId, platforms, onSearch }: Props) {
  const navigate = useNavigate();

  /* One tab per source, because a product searched on both could only ever
   * show whichever ran last. Running Hacker News hid the GitHub results
   * even though both were sitting in the table - the card just had no way
   * to ask for a particular one. */
  const [platform, setPlatform] = useState(platforms[0] ?? "github");

  const [run, setRun] = useState<OpportunityRun | null>(null);
  /** The last search that produced something, when the newest one failed. */
  const [fallback, setFallback] = useState<OpportunityRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* A failed run must not bury a good one.
   *
   * "Latest" means most recent, and most recent is sometimes a failure —
   * one bad click, and a card that had ten leads in it shows a red box and
   * nothing else. The results were never lost; they just stopped being the
   * newest thing. Falling back to the last search that actually produced
   * something keeps the failure visible without throwing the work away. */
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFallback(null);
    try {
      const newest = await productApi.lastSearch(productId, platform);
      setRun(newest);

      if (newest && newest.state === "failed") {
        const history = await productApi.searchHistory(productId);
        const good = history.find(
          (h) =>
            h.platform === platform && h.state === "succeeded" && h.result_count > 0,
        );
        if (good) setFallback(await productApi.opportunityRun(good.id));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [productId, platform]);

  useEffect(() => {
    void load();
  }, [load]);

  // Whichever run actually has results in it, which after a failure is not
  // the newest one.
  const shown = fallback ?? run;
  const results = shown?.results ?? [];
  const top = [...results].sort((a, b) => b.score - a.score).slice(0, PREVIEW);
  const running = run?.state === "running" || run?.state === "queued";
  const best = top[0]?.score ?? 0;

  const tabs = platforms.length > 1 && (
    <Stack direction="row" gap={0.5} sx={{ mb: 1.5 }}>
      {platforms.map((key) => {
        const active = key === platform;
        return (
          <Box
            component="button"
            key={key}
            onClick={() => setPlatform(key)}
            sx={{
              px: 1.75,
              py: 0.85,
              border: 1,
              cursor: "pointer",
              borderRadius: 2,
              font: "inherit",
              fontSize: 13,
              fontWeight: active ? 660 : 560,
              color: active ? "primary.main" : "text.secondary",
              borderColor: (t) =>
                active ? alpha(t.palette.primary.main, 0.4) : hairline(t),
              bgcolor: (t) =>
                active ? alpha(t.palette.primary.main, 0.09) : "transparent",
              transition: "background-color .18s ease, border-color .18s ease",
              "&:hover": {
                bgcolor: (t) =>
                  alpha(active ? t.palette.primary.main : t.palette.text.primary, 0.07),
              },
            }}
          >
            {platformName(key)}
          </Box>
        );
      })}
    </Stack>
  );

  if (loading) {
    return (
      <Box>
        {tabs}
        <Surface padding={{ xs: 2.5, md: 3 }}>
          <Skeleton variant="text" width={180} height={28} />
          <Skeleton variant="rounded" height={64} sx={{ mt: 2, borderRadius: 2 }} />
          <Skeleton variant="rounded" height={64} sx={{ mt: 1, borderRadius: 2 }} />
        </Surface>
      </Box>
    );
  }

  return (
    <Box>
    {tabs}
    <Surface accent={results.length > 0 ? "success" : "none"} sx={{ overflow: "hidden" }}>
      {/* ------------------------------------------------------- header */}
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "stretch", sm: "center" }}
        gap={2}
        sx={{ px: { xs: 2.5, md: 3 }, py: 2.5 }}
      >
        <Stack direction="row" alignItems="center" gap={1.75} sx={{ minWidth: 0 }}>
          <IconTile tone={results.length > 0 ? "success" : "muted"}>
            <HistoryIcon />
          </IconTile>
          <Box sx={{ minWidth: 0 }}>
            <Label>Latest on {platformName(platform)}</Label>
            <Typography
              sx={{ fontWeight: 690, fontSize: 17.5, letterSpacing: "-.015em", lineHeight: 1.3 }}
            >
              {headline(run, results.length)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {when(run)}
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" gap={1} sx={{ flexShrink: 0 }}>
          {/* `shown`, not `run` — after a failure these are different runs,
              and linking to the failed one would open an empty screen. */}
          {results.length > 0 && shown && (
            <Button
              endIcon={<ArrowForwardIcon />}
              onClick={() => navigate(`/opportunities?run=${shown.id}`)}
              sx={{ borderRadius: 2 }}
            >
              See all {results.length}
            </Button>
          )}
          <Button
            variant="contained"
            startIcon={<SearchIcon />}
            onClick={() => onSearch(platform)}
            disabled={running}
            sx={{ borderRadius: 2, flexShrink: 0 }}
          >
            {running ? "Running…" : run ? "Search again" : "Search now"}
          </Button>
        </Stack>
      </Stack>

      {error && (
        <Box sx={{ px: { xs: 2.5, md: 3 }, pb: 2.5 }}>
          <Alert severity="error" sx={{ borderRadius: 2 }}>
            {error}
          </Alert>
        </Box>
      )}

      {/* A failed run is worth showing rather than hiding: it is usually a
          plan with no terms, and the fix is on this very page. */}
      {run?.state === "failed" && (
        <Box sx={{ px: { xs: 2.5, md: 3 }, pb: 2.5 }}>
          <Alert severity="warning" sx={{ borderRadius: 2 }}>
            {run.error || "That search failed."}
            {fallback && (
              <Box component="span" sx={{ display: "block", mt: 0.5, opacity: 0.85 }}>
                Showing the {fallback.results.length} results from your last successful
                search instead — nothing was lost.
              </Box>
            )}
          </Alert>
        </Box>
      )}

      {/* -------------------------------------------------------- leads */}
      {top.length > 0 ? (
        <Box sx={{ borderTop: 1, borderColor: (t) => hairline(t) }}>
          {top.map((o) => (
            <Lead key={o.id} lead={o} best={best} />
          ))}

          {results.length > top.length && shown && (
            <Box
              component="button"
              onClick={() => navigate(`/opportunities?run=${shown.id}`)}
              sx={{
                width: "100%",
                border: 0,
                cursor: "pointer",
                bgcolor: "transparent",
                px: { xs: 2.5, md: 3 },
                py: 1.75,
                borderTop: 1,
                borderColor: (t) => hairline(t),
                color: "primary.main",
                font: "inherit",
                fontWeight: 600,
                fontSize: 13,
                textAlign: "left",
                transition: "background-color .18s ease",
                "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
              }}
            >
              and {results.length - top.length} more →
            </Box>
          )}
        </Box>
      ) : (
        run?.state !== "failed" && (
          <Box
            sx={{
              px: { xs: 2.5, md: 3 },
              py: 4,
              borderTop: 1,
              borderColor: (t) => hairline(t),
              textAlign: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "56ch", mx: "auto" }}>
              {run
                ? "Nothing scored well enough last time. Editing the brief above changes what this looks for."
                : `No search on ${platformName(platform)} yet. The plan below decides what this will look for.`}
            </Typography>
          </Box>
        )
      )}
    </Surface>
    </Box>
  );
}

/**
 * One lead.
 *
 * The score is the first thing on the row and set in the mono face, so a
 * column of them lines up and can be scanned without reading any titles.
 */
function Lead({ lead, best }: { lead: Opportunity; best: number }) {
  const strong = lead.score >= 45;

  return (
    <Box
      sx={{
        display: "flex",
        gap: 2,
        alignItems: "flex-start",
        px: { xs: 2.5, md: 3 },
        py: 2,
        borderTop: 1,
        borderColor: (t) => hairline(t),
        "&:first-of-type": { borderTop: 0 },
        transition: "background-color .18s ease",
        "&:hover": { bgcolor: (t) => alpha(t.palette.text.primary, 0.025) },
      }}
    >
      <Box sx={{ width: 44, flexShrink: 0, textAlign: "center" }}>
        <Typography
          sx={{
            fontFamily: MONO,
            fontSize: 19,
            fontWeight: 700,
            lineHeight: 1.1,
            color: strong ? "error.main" : "text.secondary",
          }}
        >
          {lead.score}
        </Typography>
        {/* A bar rather than a second number: the eye compares lengths far
            faster than it compares digits. */}
        <Box
          sx={{
            mt: 0.75,
            height: 3,
            borderRadius: 2,
            bgcolor: (t) => alpha(t.palette.text.primary, 0.1),
            overflow: "hidden",
          }}
        >
          <Box
            sx={{
              height: "100%",
              width: `${Math.max(8, best ? (lead.score / best) * 100 : 0)}%`,
              borderRadius: 2,
              bgcolor: strong ? "error.main" : "text.disabled",
            }}
          />
        </Box>
      </Box>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box
          component="a"
          href={lead.url}
          target="_blank"
          rel="noopener noreferrer"
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.6,
            color: "text.primary",
            textDecoration: "none",
            "&:hover": { color: "primary.main", textDecoration: "underline" },
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.5 }}>
            {lead.title}
          </Typography>
          <OpenInNewIcon sx={{ fontSize: 13, flexShrink: 0, opacity: 0.6 }} />
        </Box>

        <Stack direction="row" alignItems="center" flexWrap="wrap" gap={0.75} sx={{ mt: 0.75 }}>
          <Typography
            sx={{ fontFamily: MONO, fontSize: 11.5, color: "text.secondary" }}
            noWrap
          >
            {lead.container}
          </Typography>
          {lead.intent && (
            <Chip
              size="small"
              label={lead.intent.replace(/_/g, " ").toLowerCase()}
              sx={{
                height: 19,
                fontSize: 10.5,
                fontWeight: 600,
                border: 1,
                borderColor: (t) => hairline(t),
                bgcolor: "transparent",
                color: "text.secondary",
              }}
            />
          )}
        </Stack>
      </Box>

      <Chip
        size="small"
        label={lead.band}
        color={BAND_COLOR[lead.band]}
        variant="outlined"
        sx={{ height: 21, fontSize: 10.5, flexShrink: 0, display: { xs: "none", sm: "flex" } }}
      />
    </Box>
  );
}

function headline(run: OpportunityRun | null, count: number): string {
  if (!run) return "Never searched";
  if (run.state === "running" || run.state === "queued") return "Searching now…";
  if (run.state === "failed" && count === 0) return "That search failed";
  return `${count} ${count === 1 ? "opportunity" : "opportunities"}`;
}

function when(run: OpportunityRun | null): string {
  if (!run) return "The plan below decides what to look for";
  if (run.state === "running" || run.state === "queued") return "This takes a few minutes";
  if (!run.started_at) return "";
  return new Date(run.started_at).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
