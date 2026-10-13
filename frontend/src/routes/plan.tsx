import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CampaignIcon from "@mui/icons-material/CampaignOutlined";
import EventNoteIcon from "@mui/icons-material/EventNoteOutlined";
import LightbulbIcon from "@mui/icons-material/LightbulbOutlined";
import PeopleIcon from "@mui/icons-material/PeopleAltOutlined";
import RouteIcon from "@mui/icons-material/RouteOutlined";

import { ErrorBlock, Loading } from "@/components/StateBlocks";
import LatestResults from "@/features/plan/LatestResults";
import PlanHero from "@/features/plan/PlanHero";
import PlatformCard from "@/features/plan/PlatformCard";
import ProductBrief from "@/features/plan/ProductBrief";
import { IconTile, Label, SectionHead, Surface, hairline } from "@/components/ui";
import {
  productApi,
  type PlanPlatform,
  type PlanResult,
  type Product,
} from "@/lib/productApi";

/** How long to keep polling before assuming something went wrong. */
const POLL_MS = 3000;
const GIVE_UP_AFTER = 30;

/** The page never runs wider than this, so no line of prose gets unreadable. */
const PAGE = 1240;

export default function PlanRoute() {
  const { productId = "" } = useParams();
  const navigate = useNavigate();

  const [product, setProduct] = useState<Product | null>(null);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const attempts = useRef(0);

  const load = useCallback(async () => {
    const [p, plan] = await Promise.all([
      productApi.get(productId),
      productApi.plan(productId),
    ]);
    setProduct(p);
    setResult(plan);
    return plan;
  }, [productId]);

  // First load.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const plan = await load();
        if (!alive) return;
        // The plan writes itself after a crawl. Arriving here before it has
        // finished is normal, so wait rather than showing an empty page.
        if (!plan) setWriting(true);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [load]);

  // Poll while it is being written.
  useEffect(() => {
    if (!writing) return;

    const timer = window.setInterval(async () => {
      attempts.current += 1;
      try {
        const plan = await load();
        if (plan) {
          setWriting(false);
          attempts.current = 0;
        } else if (attempts.current >= GIVE_UP_AFTER) {
          setWriting(false);
          setError("The plan is taking longer than expected. Try writing it again.");
        }
      } catch (e) {
        setWriting(false);
        setError(e instanceof Error ? e.message : String(e));
      }
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [writing, load]);

  const write = async (force: boolean) => {
    setError(null);
    try {
      await productApi.makePlan(productId, force);
      attempts.current = 0;
      setWriting(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const findOpportunities = (
    platform: PlanPlatform,
    terms: string[],
    repos: string[],
  ) => {
    // Whatever is on the card right now, which may be what the agent chose
    // or what the user corrected. The search screen never has to ask again.
    const params = new URLSearchParams({
      product: productId,
      platform: platform.key,
      terms: terms.join("|"),
      repos: repos.join("|"),
      new: "1",
    });
    navigate(`/opportunities?${params.toString()}`);
  };

  if (loading) return <Loading label="Opening the plan" />;

  const plan = result?.plan;
  // What the AI decided this product's world is, which is a far better
  // repository search than the product's own name.
  const topic = product?.profile?.domain || product?.name || "";

  const ready = plan?.platforms.filter((p) => p.availableNow) ?? [];
  const soon = plan?.platforms.filter((p) => p.searchable && !p.availableNow) ?? [];
  const byHand = plan?.platforms.filter((p) => !p.searchable) ?? [];

  return (
    <Shell>
      <PlanHero
        name={product?.name ?? "Product"}
        domain={product?.domain}
        rewriting={writing}
        onRewrite={plan ? () => write(true) : undefined}
        stats={
          product
            ? [
                { value: product.pageCount, label: "Pages read" },
                ...(plan ? [{ value: plan.platforms.length, label: "Channels" }] : []),
                ...(ready.length ? [{ value: ready.length, label: "Searchable" }] : []),
                ...(result?.madeAt
                  ? [{ value: shortDate(result.madeAt), label: "Written" }]
                  : []),
              ]
            : []
        }
      />

      {error && <ErrorBlock message={error} onRetry={() => window.location.reload()} />}

      {/* ------------------------------------------------------- writing */}
      {writing && (
        <Surface sx={{ overflow: "hidden" }}>
          <LinearProgress />
          <Stack direction="row" gap={2} sx={{ p: { xs: 2.5, md: 3.5 } }}>
            <IconTile tone="primary" size={44}>
              <AutoAwesomeIcon />
            </IconTile>
            <Box>
              <Typography sx={{ fontWeight: 690, fontSize: 18, letterSpacing: "-.015em" }}>
                Writing the plan
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "62ch", mt: 0.5 }}>
                Reading what your website says, working out who to reach and where. This
                takes about half a minute.
              </Typography>
            </Box>
          </Stack>
        </Surface>
      )}

      {/* --------------------------------------------------------- empty */}
      {!plan && !writing && (
        <Surface sx={{ px: 3, py: { xs: 6, md: 9 }, textAlign: "center" }}>
          <Box sx={{ display: "inline-flex", mb: 2 }}>
            <IconTile tone="primary" size={52}>
              <AutoAwesomeIcon />
            </IconTile>
          </Box>
          <Typography sx={{ fontWeight: 700, fontSize: 22, letterSpacing: "-.02em", mb: 1 }}>
            No plan yet
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 3.5, maxWidth: "50ch", mx: "auto", lineHeight: 1.7 }}
          >
            {product?.state === "ready"
              ? "The website has been read. Write the marketing plan from it."
              : "The website needs to be read first — a plan written without it is generic advice."}
          </Typography>
          <Button
            variant="contained"
            size="large"
            startIcon={<AutoAwesomeIcon />}
            onClick={() => write(false)}
            disabled={product?.state === "crawling" || product?.state === "queued"}
            sx={{ borderRadius: 2, px: 3.5, py: 1.3 }}
          >
            Write the plan
          </Button>
        </Surface>
      )}

      {/* ---------------------------------------------------------- plan */}
      {plan && (
        <>
          {/* The payoff first.
              The plan explains what we are looking for; this is what was
              actually found. Reading the explanation before the result is
              the wrong way round on every visit after the first. */}
          {ready.length > 0 && (
            <Box component="section">
              <SectionHead
                title="Latest search"
                tone="live"
                hint={
                  ready.length > 1
                    ? "What the plan below actually found. Each source keeps its own results."
                    : `What the plan below actually found on ${ready[0].name}.`
                }
              />
              <LatestResults
                productId={productId}
                platforms={ready.map((p) => p.key)}
                onSearch={(key) => {
                  // Search the platform being looked at, with that card's
                  // own terms - not whichever one happens to be first.
                  const card = ready.find((p) => p.key === key) ?? ready[0];
                  findOpportunities(card, card.searchTerms, card.targetPlaces);
                }}
              />
            </Box>
          )}

          {/* The brief and the strategy it produced, side by side.
              Cause on the left, effect on the right — and because the brief
              is editable, the thing you change sits next to the thing that
              changes. */}
          <Box component="section">
            <SectionHead
              title="The thinking"
              hint="Your brief is the input. Everything to the right of it was written from that."
            />
            <Box
              sx={{
                display: "grid",
                gap: 2.5,
                alignItems: "stretch",
                gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 5fr) minmax(0, 7fr)" },
              }}
            >
              {product && (
                <ProductBrief
                  product={product}
                  stale={result?.stale ?? false}
                  onSaved={load}
                  onRewrite={() => write(true)}
                />
              )}

              <Surface sx={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
                <Pillar
                  icon={<RouteIcon />}
                  title="Strategy"
                  body={plan.strategy}
                />
                <Pillar
                  icon={<PeopleIcon />}
                  title="Who to reach"
                  body={plan.audience}
                  divided
                />
                <Pillar
                  icon={<CampaignIcon />}
                  title="How to describe it"
                  body={plan.positioning}
                  divided
                />
              </Surface>
            </Box>
          </Box>

          {/* ------------------------------------------------- channels */}
          <Group
            title="Search these now"
            hint="We can find real posts here. Press the button to see who is asking."
            count={ready.length}
            tone="live"
            platforms={ready}
            columns={1}
            topic={topic}
            onFind={findOpportunities}
          />

          <Group
            title="Do these by hand"
            hint="We cannot search these. The plan says what to do there and in what voice."
            count={byHand.length}
            platforms={byHand}
            columns={3}
          />

          <Group
            title="Coming soon"
            hint="We will be able to search these once the connector is built."
            count={soon.length}
            platforms={soon}
            columns={3}
          />

          {/* ---------------------------------------------------- doing */}
          <Box component="section">
            <SectionHead
              title="What to do next"
              hint="Written for this product, not general advice."
            />
            <Box
              sx={{
                display: "grid",
                gap: 2.5,
                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
              }}
            >
              <ListCard
                icon={<LightbulbIcon />}
                title="What to write about"
                items={plan.contentIdeas}
              />
              <ListCard
                icon={<EventNoteIcon />}
                title="First week"
                items={plan.firstWeek}
                numbered
              />
            </Box>
          </Box>
        </>
      )}
    </Shell>
  );
}

/* ------------------------------------------------------------------ */

/**
 * The page frame.
 *
 * AppShell renders its children bare, so every route brings its own
 * padding. This one had none, which is why the title sat welded to the
 * toolbar and the content touched the window edge on a narrow screen.
 */
function Shell({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ maxWidth: PAGE, mx: "auto", px: { xs: 2, sm: 3 }, py: { xs: 3, md: 4.5 } }}>
      <Stack gap={{ xs: 3.5, md: 5 }}>{children}</Stack>
    </Box>
  );
}

/** Written 26 Aug. Not "3 days ago", which needs a tick to stay true. */
function shortDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * One third of the strategy.
 *
 * Stacked rather than in three columns. Side by side these ran to about
 * thirty characters a line at desktop width — a shape that is harder to
 * read than the long line it was meant to fix.
 */
function Pillar({
  icon,
  title,
  body,
  divided = false,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  divided?: boolean;
}) {
  return (
    <Box
      sx={{
        p: { xs: 2.5, md: 3 },
        flex: 1,
        ...(divided && { borderTop: 1, borderColor: (t) => hairline(t) }),
      }}
    >
      <Stack direction="row" alignItems="center" gap={1.25} sx={{ mb: 1.25 }}>
        <Box sx={{ color: "primary.main", display: "flex", "& svg": { fontSize: 17 } }}>
          {icon}
        </Box>
        <Label>{title}</Label>
      </Stack>
      <Typography variant="body2" sx={{ lineHeight: 1.75 }}>
        {body || <Box component="span" sx={{ color: "text.disabled" }}>—</Box>}
      </Typography>
    </Box>
  );
}

function Group({
  title,
  hint,
  count,
  tone,
  platforms,
  columns,
  topic,
  onFind,
}: {
  title: string;
  hint: string;
  count: number;
  tone?: "live";
  platforms: PlanPlatform[];
  /** How many the row holds at desktop width. One means the card goes wide. */
  columns: 1 | 2 | 3;
  topic?: string;
  onFind?: (p: PlanPlatform, terms: string[], repos: string[]) => void;
}) {
  if (platforms.length === 0) return null;

  // Never more columns than cards, which is what left the void in the old
  // layout: three columns, one card, two thirds of nothing.
  const cols = Math.min(columns, platforms.length);
  const wide = cols === 1;

  return (
    <Box component="section">
      <SectionHead title={title} hint={hint} count={count} tone={tone} />
      <Box
        sx={{
          display: "grid",
          gap: 2.5,
          alignItems: "stretch",
          gridTemplateColumns: {
            xs: "1fr",
            sm: cols > 1 ? "repeat(2, minmax(0, 1fr))" : "1fr",
            md: `repeat(${cols}, minmax(0, 1fr))`,
          },
        }}
      >
        {platforms.map((p) => (
          <PlatformCard
            key={p.key || p.name}
            platform={p}
            topic={topic}
            wide={wide}
            onFindOpportunities={onFind}
          />
        ))}
      </Box>
    </Box>
  );
}

function ListCard({
  icon,
  title,
  items,
  numbered = false,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
  numbered?: boolean;
}) {
  if (items.length === 0) return null;

  return (
    <Surface sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Stack
        direction="row"
        alignItems="center"
        gap={1.5}
        sx={{
          px: { xs: 2.5, md: 3 },
          py: 2.25,
          borderBottom: 1,
          borderColor: (t) => hairline(t),
        }}
      >
        <IconTile tone="primary" size={34}>
          {icon}
        </IconTile>
        <Typography sx={{ fontWeight: 680, fontSize: 16.5, letterSpacing: "-.01em" }}>
          {title}
        </Typography>
      </Stack>

      <Stack sx={{ p: { xs: 2.5, md: 3 } }} gap={2}>
        {items.map((item, i) => (
          // Index in the key because the model does occasionally repeat a
          // line, and two identical keys drop one of them silently.
          <Stack key={`${i}-${item}`} direction="row" gap={1.75} alignItems="flex-start">
            {numbered ? (
              <Box
                sx={{
                  width: 23,
                  height: 23,
                  mt: 0.1,
                  flexShrink: 0,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 11.5,
                  fontWeight: 700,
                  border: 1,
                  borderColor: (t) => alpha(t.palette.primary.main, 0.35),
                  bgcolor: (t) => alpha(t.palette.primary.main, 0.1),
                  color: "primary.main",
                }}
              >
                {i + 1}
              </Box>
            ) : (
              <Box
                sx={{
                  width: 5,
                  height: 5,
                  mt: 1,
                  flexShrink: 0,
                  borderRadius: "50%",
                  bgcolor: "primary.main",
                  opacity: 0.55,
                }}
              />
            )}
            <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
              {item}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Surface>
  );
}
