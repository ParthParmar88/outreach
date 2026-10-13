import { useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import AddIcon from "@mui/icons-material/Add";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DescriptionIcon from "@mui/icons-material/DescriptionOutlined";
import HistoryIcon from "@mui/icons-material/HistoryToggleOff";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";

import { ErrorBlock, Loading } from "@/components/StateBlocks";
import { IconTile, Label, SectionHead, Surface, hairline } from "@/components/ui";
import { BAND_COLOR, platformName } from "@/features/opportunities/band";
import { useAuth } from "@/lib/auth";
import {
  productApi,
  type LeadState,
  type Opportunity,
  type OpportunityRun,
  type SearchSummary,
} from "@/lib/productApi";
import { useSelectedProduct } from "@/lib/selectedProduct";
import { MONO } from "@/styles/theme";

/** How many leads the card shows before sending you to the full list. */
const PREVIEW = 5;

/** A live run is still moving, so keep asking. */
const POLL_MS = 4000;

/**
 * Where signing in lands you.
 *
 * The last search comes first, because that is the thing somebody comes
 * back to look at. Which product you are on is chosen in the top bar now,
 * so this screen is the workspace for whatever is selected rather than a
 * picker with a placeholder underneath it.
 */
export default function HomeRoute() {
  const { user } = useAuth();
  const { products, selected, loading, error } = useSelectedProduct();

  const [run, setRun] = useState<OpportunityRun | null>(null);
  /** The last search that produced something, when the newest one failed. */
  const [fallback, setFallback] = useState<OpportunityRun | null>(null);
  const [history, setHistory] = useState<SearchSummary[]>([]);
  const [counts, setCounts] = useState<Record<LeadState, number> | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);

  /* Which source is being reviewed.
   *
   * Empty means "whatever ran last", which is the right answer before any
   * history has loaded and the wrong one after: a product searched on both
   * could only ever see the newer source, and the older one's results were
   * reachable only by hunting through Earlier searches for a small label. */
  const [platform, setPlatform] = useState("");

  const productId = selected?.id ?? "";

  // A source chosen for one product means nothing for the next one.
  useEffect(() => setPlatform(""), [productId]);

  useEffect(() => {
    if (!productId) {
      setRun(null);
      setHistory([]);
      setCounts(null);
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const fetchOnce = async () => {
      try {
        // Together, because the history is what tells you whether the last
        // search is the only one or the newest of ten.
        const [found, past] = await Promise.all([
          productApi.lastSearch(productId, platform || undefined),
          productApi.searchHistory(productId),
        ]);
        if (cancelled) return;
        setRun(found);
        setHistory(past);
        setRunError(null);

        if (found && found.state === "failed") {
          const good = past.find(
            (h) =>
              (!platform || h.platform === platform) &&
              h.state === "succeeded" &&
              h.result_count > 0,
          );
          if (good) {
            const recovered = await productApi.opportunityRun(good.id);
            if (!cancelled) setFallback(recovered);
          }
        } else if (!cancelled) {
          setFallback(null);
        }

        // Keep watching only while something is actually happening.
        if (found && (found.state === "queued" || found.state === "running")) {
          timer = window.setTimeout(() => void fetchOnce(), POLL_MS);
        }
      } catch (e) {
        if (!cancelled) setRunError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoadingRun(false);
      }
    };

    setLoadingRun(true);
    setRun(null);
    setHistory([]);
    void fetchOnce();

    // Separate from the run, because lead state changes when a person
    // presses a button rather than while a search runs.
    (async () => {
      try {
        const found = await productApi.leads(productId);
        if (!cancelled) setCounts(found.counts);
      } catch {
        // The counts are a nicety. A home page without them still works.
      }
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [productId, platform]);

  if (error) {
    return (
      <Page>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Page>
    );
  }

  if (loading) {
    return (
      <Page>
        <Loading label="Loading your products" />
      </Page>
    );
  }

  /* ------------------------------------------------------ no products */
  if (products.length === 0) {
    return (
      <Page>
        <Surface sx={{ px: 3, py: { xs: 7, md: 10 }, textAlign: "center" }}>
          <Box sx={{ display: "inline-flex", mb: 2.5 }}>
            <IconTile tone="primary" size={54}>
              <AddIcon />
            </IconTile>
          </Box>
          <Typography sx={{ fontWeight: 700, fontSize: 24, letterSpacing: "-.025em", mb: 1 }}>
            Add your first product
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: "46ch", mx: "auto", mb: 4, lineHeight: 1.75 }}
          >
            We read its website to learn what it does, write a marketing plan from
            that, and then go and find people describing the problem it solves.
          </Typography>
          <Button
            component={RouterLink}
            to="/new"
            variant="contained"
            size="large"
            startIcon={<AddIcon />}
            sx={{ px: 3.5, py: 1.3 }}
          >
            Add a product
          </Button>
        </Surface>
      </Page>
    );
  }

  const running = run?.state === "queued" || run?.state === "running";
  // Whichever run actually has results in it, which after a failure is not
  // the newest one.
  const shown = fallback ?? run;
  const results = shown?.results ?? [];
  const top = results.slice(0, PREVIEW);
  const best = top[0]?.score ?? 0;

  /* Tabs come from what has actually been searched, newest source first.
   *
   * Not from the plan. Home is where results are reviewed, not where
   * searches are started, so offering a tab for a source with nothing
   * behind it would be an empty promise - the plan page is where a new
   * source gets run for the first time. */
  const sources: string[] = [];
  for (const entry of history) {
    if (!sources.includes(entry.platform)) sources.push(entry.platform);
  }

  // Which source the rows below belong to. Blank until a tab is pressed,
  // and then it is whatever the newest run happened to be.
  const viewing = platform || run?.platform || sources[0] || "github";
  const earlier = history.filter((h) => h.platform === viewing).slice(1);

  return (
    <Page>
      {/* ---------------------------------------------------------- hero */}
      <Box
        sx={{
          position: "relative",
          overflow: "hidden",
          borderRadius: 3,
          border: 1,
          borderColor: (t) => hairline(t),
          bgcolor: "background.paper",
          backgroundImage: (t) => `
            radial-gradient(110% 130% at 90% -25%, ${alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.24 : 0.14)} 0%, transparent 60%),
            linear-gradient(180deg, ${alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.08 : 0.05)} 0%, transparent 74%)
          `,
          px: { xs: 2.5, md: 4 },
          py: { xs: 3, md: 4 },
        }}
      >
        <Stack
          direction={{ xs: "column", md: "row" }}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "flex-end" }}
          gap={2.5}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography
              sx={{
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: ".18em",
                textTransform: "uppercase",
                color: "primary.main",
                mb: 0.75,
              }}
            >
              {greeting()}
            </Typography>
            <Typography
              component="h1"
              sx={{
                fontSize: { xs: 28, md: 36 },
                fontWeight: 720,
                letterSpacing: "-.032em",
                lineHeight: 1.12,
              }}
            >
              {user?.name ?? "Welcome"}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.25 }}>
              Working on <b>{selected?.name}</b> — switch products in the bar above.
            </Typography>
          </Box>

          <Stack direction="row" gap={1.25} sx={{ flexShrink: 0 }}>
            <Button
              component={RouterLink}
              to={`/products/${productId}/plan`}
              variant="outlined"
              startIcon={<AutoAwesomeIcon />}
              sx={{ bgcolor: "background.paper", borderColor: (t) => alpha(t.palette.primary.main, 0.35) }}
            >
              Marketing plan
            </Button>
            <Button
              component={RouterLink}
              to={`/opportunities?product=${productId}&platform=${viewing}&new=1`}
              variant="contained"
              startIcon={<SearchIcon />}
              disabled={running}
            >
              {run ? "Search again" : "Search now"}
            </Button>
          </Stack>
        </Stack>

        {/* The pipeline in four figures. These come from the lead table, so
            they are what is left to do rather than what the last search
            happened to return. */}
        {counts && (
          <Stack
            direction="row"
            flexWrap="wrap"
            gap={{ xs: 2.5, md: 5 }}
            sx={{
              mt: { xs: 3, md: 3.5 },
              pt: { xs: 2.5, md: 3 },
              borderTop: 1,
              borderColor: (t) => hairline(t),
            }}
          >
            <Stat value={counts.new} label="To work" accent />
            <Stat value={counts.replied} label="Replied" />
            <Stat value={counts.won} label="Won" />
            <Stat value={counts.ignored} label="Ignored" />
          </Stack>
        )}
      </Box>

      {runError && <ErrorBlock message={runError} />}

      {/* ---------------------------------------------------- last search */}
      {loadingRun && <Loading label="Looking for your last search" />}

      {!loadingRun && !run && !runError && (
        <Surface sx={{ px: 3, py: { xs: 6, md: 8 }, textAlign: "center" }}>
          <Box sx={{ display: "inline-flex", mb: 2 }}>
            <IconTile tone="muted" size={46}>
              <SearchIcon />
            </IconTile>
          </Box>
          <Typography sx={{ fontWeight: 690, fontSize: 19, letterSpacing: "-.02em", mb: 1 }}>
            No searches yet
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: "50ch", mx: "auto", lineHeight: 1.7 }}
          >
            {selected?.state === "ready"
              ? "Open the marketing plan and press Find opportunities, or search straight away with the plan's own terms."
              : "The website has not been read yet, so a search would have nothing to match against."}
          </Typography>
        </Surface>
      )}

      {sources.length > 1 && (
        <Stack direction="row" gap={0.75} sx={{ mt: -1 }}>
          {sources.map((key) => {
            const active = key === viewing;
            const runs = history.filter((h) => h.platform === key).length;
            return (
              <Box
                component="button"
                key={key}
                onClick={() => setPlatform(key)}
                sx={{
                  px: 2,
                  py: 1,
                  border: 1,
                  cursor: "pointer",
                  borderRadius: 2,
                  font: "inherit",
                  fontSize: 13.5,
                  fontWeight: active ? 660 : 560,
                  color: active ? "primary.main" : "text.secondary",
                  borderColor: (t) =>
                    active ? alpha(t.palette.primary.main, 0.4) : hairline(t),
                  bgcolor: (t) =>
                    active ? alpha(t.palette.primary.main, 0.09) : "background.paper",
                  transition: "background-color .18s ease, border-color .18s ease",
                  "&:hover": {
                    bgcolor: (t) =>
                      alpha(
                        active ? t.palette.primary.main : t.palette.text.primary,
                        0.07,
                      ),
                  },
                }}
              >
                {platformName(key)}
                <Box
                  component="span"
                  sx={{ ml: 0.75, opacity: 0.6, fontWeight: 560, fontSize: 12 }}
                >
                  {runs}
                </Box>
              </Box>
            );
          })}
        </Stack>
      )}

      {run && (
        <Surface accent={results.length > 0 ? "success" : "none"} sx={{ overflow: "hidden" }}>
          {running && <LinearProgress variant="determinate" value={run.percent} />}

          <Stack
            direction={{ xs: "column", sm: "row" }}
            alignItems={{ xs: "stretch", sm: "center" }}
            justifyContent="space-between"
            gap={2}
            sx={{ px: { xs: 2.5, md: 3 }, py: 2.5 }}
          >
            <Stack direction="row" alignItems="center" gap={1.75} sx={{ minWidth: 0 }}>
              <IconTile tone={results.length > 0 ? "success" : "muted"}>
                <HistoryIcon />
              </IconTile>
              <Box sx={{ minWidth: 0 }}>
                <Label>Last search</Label>
                <Typography
                  sx={{ fontWeight: 700, fontSize: 20, letterSpacing: "-.022em", lineHeight: 1.25 }}
                >
                  {running
                    ? "Searching…"
                    : run.state === "failed"
                      ? "Search failed"
                      : `${results.length} ${results.length === 1 ? "opportunity" : "opportunities"}`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  on {platformName(run.platform)}
                  {run.started_at && ` · ${when(run.started_at)}`}
                </Typography>
              </Box>
            </Stack>

            {/* `shown`, not `run`. After a failure they are different runs,
                and pointing at the failed one opens an empty screen. */}
            <Button
              component={RouterLink}
              to={`/opportunities?run=${(shown ?? run).id}`}
              endIcon={<ArrowForwardIcon />}
              sx={{ flexShrink: 0 }}
            >
              {running ? "Watch it run" : "See all results"}
            </Button>
          </Stack>

          {run.error && (
            <Box sx={{ px: { xs: 2.5, md: 3 }, pb: 2.5 }}>
              <Typography variant="body2" color="error.main">
                {run.error}
                {fallback && (
                  <Box component="span" sx={{ display: "block", mt: 0.5, opacity: 0.85 }}>
                    Showing the {fallback.results.length} results from your last successful
                    search instead — nothing was lost.
                  </Box>
                )}
              </Typography>
            </Box>
          )}

          {top.length > 0 && (
            <Box sx={{ borderTop: 1, borderColor: (t) => hairline(t) }}>
              {top.map((item) => (
                <ResultRow key={item.id} item={item} best={best} />
              ))}
            </Box>
          )}

          {results.length > PREVIEW && shown && (
            <Box
              component={RouterLink}
              to={`/opportunities?run=${shown.id}`}
              sx={{
                display: "block",
                px: { xs: 2.5, md: 3 },
                py: 1.75,
                borderTop: 1,
                borderColor: (t) => hairline(t),
                color: "primary.main",
                fontWeight: 620,
                fontSize: 13,
                textDecoration: "none",
                transition: "background-color .18s ease",
                "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
              }}
            >
              and {results.length - PREVIEW} more →
            </Box>
          )}

          {!running && run.state === "succeeded" && results.length === 0 && (
            <Box
              sx={{
                px: { xs: 2.5, md: 3 },
                py: 3.5,
                borderTop: 1,
                borderColor: (t) => hairline(t),
              }}
            >
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
                Nothing came back. That usually means the plan searched too narrowly
                rather than that nobody has the problem — open the results to read what
                each query returned.
              </Typography>
            </Box>
          )}
        </Surface>
      )}

      {/* ------------------------------------------------------- history */}
      {/* Everything before the newest one. Opening any of them reads the
          stored result and never starts another search. */}
      {earlier.length > 0 && (
        <Box component="section">
          <SectionHead
            title={`Earlier ${platformName(viewing)} searches`}
            hint="Saved results. Opening one costs nothing."
          />
          <Surface sx={{ overflow: "hidden" }}>
            {earlier.map((entry) => (
              <Stack
                key={entry.id}
                component={RouterLink}
                to={`/opportunities?run=${entry.id}`}
                direction="row"
                alignItems="center"
                gap={2}
                sx={{
                  px: { xs: 2.5, md: 3 },
                  py: 2,
                  textDecoration: "none",
                  color: "inherit",
                  borderTop: 1,
                  borderColor: (t) => hairline(t),
                  "&:first-of-type": { borderTop: 0 },
                  transition: "background-color .18s ease",
                  "&:hover": { bgcolor: (t) => alpha(t.palette.text.primary, 0.03) },
                }}
              >
                <HistoryIcon sx={{ fontSize: 17, color: "text.disabled", flexShrink: 0 }} />

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 620 }}>
                    {entry.state === "succeeded"
                      ? `${entry.result_count} ${entry.result_count === 1 ? "opportunity" : "opportunities"}`
                      : entry.state === "failed"
                        ? "Search failed"
                        : "Still running"}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {when(entry.started_at)}
                  </Typography>
                </Box>

                {entry.top_score > 0 && (
                  <Chip
                    size="small"
                    label={`best ${entry.top_score}`}
                    variant="outlined"
                    sx={{ fontFamily: MONO, height: 22, fontSize: 11, flexShrink: 0 }}
                  />
                )}
                <ArrowForwardIcon sx={{ fontSize: 15, color: "text.disabled", flexShrink: 0 }} />
              </Stack>
            ))}
          </Surface>
        </Box>
      )}

      {/* --------------------------------------------------- quick links */}
      {selected && (
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Button
            component="a"
            href={productApi.markdownUrl(productId)}
            target="_blank"
            rel="noopener"
            size="small"
            color="inherit"
            startIcon={<DescriptionIcon sx={{ fontSize: 17 }} />}
            disabled={selected.state !== "ready"}
            sx={{ color: "text.secondary" }}
          >
            What we read from the website
          </Button>
          <Button
            component={RouterLink}
            to="/settings/product"
            size="small"
            color="inherit"
            sx={{ color: "text.secondary" }}
          >
            Manage products
          </Button>
        </Stack>
      )}
    </Page>
  );
}

/* ------------------------------------------------------------------ */

function Page({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        maxWidth: 1080,
        mx: "auto",
        px: { xs: 2, sm: 3 },
        py: { xs: 3, md: 4.5 },
      }}
    >
      <Stack gap={{ xs: 3, md: 4 }}>{children}</Stack>
    </Box>
  );
}

/** Morning, afternoon or evening. A greeting that ignores the clock reads as a template. */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Stat({
  value,
  label,
  accent = false,
}: {
  value: number;
  label: string;
  accent?: boolean;
}) {
  return (
    <Box sx={{ minWidth: 64 }}>
      <Typography
        sx={{
          fontSize: { xs: 21, md: 25 },
          fontWeight: 720,
          letterSpacing: "-.03em",
          lineHeight: 1.15,
          color: accent && value > 0 ? "primary.main" : "text.primary",
        }}
      >
        {value}
      </Typography>
      <Typography
        sx={{
          fontSize: 10.5,
          fontWeight: 640,
          letterSpacing: ".1em",
          textTransform: "uppercase",
          color: "text.secondary",
          mt: 0.25,
        }}
      >
        {label}
      </Typography>
    </Box>
  );
}

/**
 * One lead on the home page.
 *
 * The bar under the score is doing the comparing: a column of numbers has
 * to be read one at a time, where a column of bars is taken in at a glance.
 */
function ResultRow({ item, best }: { item: Opportunity; best: number }) {
  const strong = item.score >= 45;

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
      <Box sx={{ width: 46, flexShrink: 0, textAlign: "center" }}>
        <Typography
          sx={{
            fontFamily: MONO,
            fontSize: 19,
            fontWeight: 700,
            lineHeight: 1.1,
            color: strong ? "error.main" : "text.secondary",
          }}
        >
          {item.score}
        </Typography>
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
              width: `${Math.max(8, best ? (item.score / best) * 100 : 0)}%`,
              borderRadius: 2,
              bgcolor: strong ? "error.main" : "text.disabled",
            }}
          />
        </Box>
      </Box>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box
          component="a"
          href={item.url}
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
          <Typography variant="body2" sx={{ fontWeight: 620, lineHeight: 1.5 }}>
            {item.title}
          </Typography>
          <OpenInNewIcon sx={{ fontSize: 13, flexShrink: 0, opacity: 0.6 }} />
        </Box>

        <Stack direction="row" alignItems="center" flexWrap="wrap" gap={0.75} sx={{ mt: 0.6 }}>
          <Typography sx={{ fontFamily: MONO, fontSize: 11.5, color: "text.secondary" }} noWrap>
            {item.container}
          </Typography>
          {item.problem && (
            <Typography variant="caption" color="text.secondary" sx={{ minWidth: 0 }} noWrap>
              · {item.problem}
            </Typography>
          )}
        </Stack>
      </Box>

      <Chip
        size="small"
        label={item.band}
        color={BAND_COLOR[item.band]}
        variant="outlined"
        sx={{ height: 21, fontSize: 10.5, flexShrink: 0, display: { xs: "none", sm: "flex" } }}
      />
    </Box>
  );
}

/** "1 Sep, 2:25 pm". Enough to tell two runs on the same day apart. */
function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}
