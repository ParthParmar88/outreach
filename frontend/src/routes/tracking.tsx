import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";

import ProductTabs from "@/components/ProductTabs";
import { ErrorBlock, Loading } from "@/components/StateBlocks";
import {
  trackingApi,
  type Funnel,
  type Outcome,
  type TrackedPost,
} from "@/lib/trackingApi";
import { MONO } from "@/styles/theme";

/** The funnel, in order. Each stage keeps a subset of the one before it. */
const STAGES: { key: keyof Funnel; label: string; how: string; says: string }[] = [
  {
    key: "drafted",
    label: "Drafted",
    how: "automatic",
    says: "You asked for a reply — the first sign you judged one worth answering.",
  },
  {
    key: "posted",
    label: "Posted",
    how: "you said so",
    says: "You actually replied on the thread.",
  },
  {
    key: "answered",
    label: "Answered",
    how: "automatic",
    says: "Somebody responded after your comment.",
  },
  {
    key: "skipped",
    label: "Skipped",
    how: "decided against",
    says: "Not worth replying to — kept so a later search knows.",
  },
];

const OUTCOMES: { value: Outcome; label: string }[] = [
  { value: "ignored", label: "Ignored" },
  { value: "conversation", label: "Conversation" },
  { value: "lead", label: "Lead" },
  { value: "customer", label: "Customer" },
];

const STATE_COLOR: Record<TrackedPost["state"], "default" | "info" | "success" | "warning"> = {
  drafted: "info",
  posted: "warning",
  answered: "success",
  skipped: "default",
};

/**
 * What outreach actually did for this product.
 *
 * The honest framing, and the page says it out loud: only the outcome is
 * value. Everything before it is a leading indicator we get for free, and
 * dressing a comment count up as revenue would be worse than showing
 * nothing.
 */
export default function TrackingRoute() {
  const { productId = "" } = useParams();

  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [posts, setPosts] = useState<TrackedPost[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const board = await trackingApi.board(productId);
      setFunnel(board.funnel);
      setPosts(board.posts);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    void load();
  }, [load]);

  /* Answered is the one automatic stage nobody can press a button for: it
     means going back to each thread and looking. Asked for on opening, and
     the board reloaded only if the look found something. A failed check is
     not worth a red box - the board is still right about everything else. */
  useEffect(() => {
    trackingApi
      .checkReplies(productId)
      .then((result) => {
        if (result.changed > 0) void load();
      })
      .catch(() => {});
  }, [productId, load]);

  const setOutcome = async (post: TrackedPost, outcome: Outcome) => {
    // Optimistic: this is one click on a list of many, and a spinner per row
    // would make recording five outcomes feel like filing a form.
    setPosts((prev) => prev.map((p) => (p.id === post.id ? { ...p, outcome } : p)));
    try {
      await trackingApi.setOutcome(post.id, outcome);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      void load();
    }
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto", px: { xs: 2, sm: 3 }, py: { xs: 3, md: 5 } }}>
      <ProductTabs productId={productId} />

      <Stack gap={3}>
        <Box>
          <Typography
            variant="overline"
            sx={{ color: "text.secondary", letterSpacing: ".16em", fontSize: 10.5 }}
          >
            Tracking
          </Typography>
          <Typography
            variant="h4"
            sx={{ fontSize: { xs: 24, md: 30 }, fontWeight: 680, letterSpacing: "-.022em" }}
          >
            What outreach did
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: "68ch" }}>
            Every post you thought was worth answering, and what came of it. A
            post appears here the moment you ask for a reply.
          </Typography>
        </Box>

        {error && <ErrorBlock message={error} onRetry={() => window.location.reload()} />}
        {loading && <Loading label="Loading" />}

        {!loading && funnel && (
          <>
            <Paper
              variant="outlined"
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
                "& > * + *": {
                  borderLeft: { xs: 0, md: 1 },
                  borderColor: "divider",
                },
              }}
            >
              {STAGES.map(({ key, label, how, says }) => (
                <Stage key={key} count={funnel[key]} label={label} how={how} says={says} />
              ))}
            </Paper>

            <Typography variant="caption" color="text.secondary" sx={{ maxWidth: "72ch" }}>
              Only the <b>outcome</b> on each post below is real value. The
              counts above are leading indicators — they say what you did, not
              what it was worth.
            </Typography>
          </>
        )}

        {!loading && !error && posts.length === 0 && (
          <Paper variant="outlined" sx={{ px: 3, py: 7, textAlign: "center" }}>
            <SearchIcon sx={{ fontSize: 28, color: "text.disabled", mb: 1.5 }} />
            <Typography sx={{ fontWeight: 650, fontSize: 18, mb: 1 }}>
              Nothing tracked yet
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ maxWidth: "50ch", mx: "auto", mb: 3 }}
            >
              Run a search, then press <b>Draft a reply</b> on a post worth
              answering. It appears here straight away.
            </Typography>
            <Button
              component={RouterLink}
              to={`/opportunities?product=${productId}&new=1`}
              variant="contained"
              startIcon={<SearchIcon />}
            >
              Find opportunities
            </Button>
          </Paper>
        )}

        {posts.length > 0 && (
          <Paper variant="outlined" sx={{ overflow: "hidden" }}>
            <Stack divider={<Divider />}>
              {posts.map((post) => (
                <PostRow key={post.id} post={post} onOutcome={setOutcome} />
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Box>
  );
}

/* ------------------------------------------------------------------ */

function Stage({
  label,
  count,
  how,
  says,
}: {
  label: string;
  count: number;
  how: string;
  says: string;
}) {
  return (
    <Box sx={{ p: 2.25 }}>
      <Typography
        sx={{
          fontFamily: MONO,
          fontSize: 30,
          fontWeight: 600,
          lineHeight: 1,
          fontVariantNumeric: "tabular-nums",
          color: count > 0 ? "text.primary" : "text.disabled",
        }}
      >
        {count}
      </Typography>
      <Typography sx={{ fontWeight: 650, fontSize: 14, mt: 0.75 }}>{label}</Typography>
      <Typography
        variant="overline"
        sx={{
          display: "block",
          fontSize: 9.5,
          letterSpacing: ".1em",
          color: "text.secondary",
          lineHeight: 1.8,
        }}
      >
        {how}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        {says}
      </Typography>
    </Box>
  );
}

function PostRow({
  post,
  onOutcome,
}: {
  post: TrackedPost;
  onOutcome: (post: TrackedPost, outcome: Outcome) => void;
}) {
  return (
    <Box sx={{ px: 2.5, py: 2 }}>
      <Stack direction="row" alignItems="flex-start" gap={2} flexWrap="wrap">
        <Box sx={{ flex: 1, minWidth: 260 }}>
          <Link
            href={post.url}
            target="_blank"
            rel="noopener"
            underline="hover"
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              fontSize: 14.5,
              fontWeight: 620,
              color: "text.primary",
            }}
          >
            {post.title ?? post.url}
            <OpenInNewIcon sx={{ fontSize: 13, color: "text.disabled" }} />
          </Link>

          <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.75 }} flexWrap="wrap">
            <Chip
              size="small"
              label={post.state}
              color={STATE_COLOR[post.state]}
              variant="outlined"
              sx={{ height: 20, fontSize: 10.5 }}
            />
            <Typography sx={{ fontFamily: MONO, fontSize: 11, color: "text.secondary" }}>
              {post.container} · score {post.score_when_found}
            </Typography>
            {post.our_comment_url && (
              <Chip
                size="small"
                icon={<CheckCircleIcon sx={{ fontSize: 13 }} />}
                label="comment linked"
                variant="outlined"
                color="success"
                sx={{ height: 20, fontSize: 10.5 }}
              />
            )}
            {post.replies_after > 0 && (
              <Chip
                size="small"
                label={`${post.replies_after} replied after you`}
                color="success"
                sx={{ height: 20, fontSize: 10.5 }}
              />
            )}
          </Stack>

          {post.skip_reason && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Skipped: {post.skip_reason}
            </Typography>
          )}
        </Box>

        {/* Outcome is only meaningful once something was actually sent. */}
        {post.state === "posted" || post.state === "answered" ? (
          <Select
            size="small"
            displayEmpty
            value={post.outcome ?? ""}
            onChange={(e) => onOutcome(post, e.target.value as Outcome)}
            sx={{ minWidth: 168, flexShrink: 0 }}
            renderValue={(value) =>
              value ? (
                OUTCOMES.find((o) => o.value === value)?.label
              ) : (
                <Box component="span" sx={{ color: "text.disabled" }}>
                  What came of it?
                </Box>
              )
            }
          >
            {OUTCOMES.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </Select>
        ) : null}
      </Stack>

      {post.draft && <DraftPeek text={post.draft} />}
    </Box>
  );
}

/** The draft, collapsed. Nobody wants nine paragraphs in a list of twenty. */
function DraftPeek({ text }: { text: string }): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ mt: 1.25 }}>
      <Button size="small" onClick={() => setOpen(!open)} sx={{ px: 0, minWidth: 0 }}>
        {open ? "Hide the draft" : "Show the draft"}
      </Button>
      {open && (
        <Box
          sx={{
            mt: 1,
            p: 1.75,
            borderRadius: 1,
            border: 1,
            borderColor: "divider",
            bgcolor: "action.hover",
            whiteSpace: "pre-wrap",
            fontSize: 13.5,
            lineHeight: 1.6,
          }}
        >
          {text}
        </Box>
      )}
    </Box>
  );
}
