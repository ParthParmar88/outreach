import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";

import { ErrorBlock, Loading, PageHeader } from "@/components/StateBlocks";
import MarkdownDialog from "@/features/product/MarkdownDialog";
import { isRunning, productApi, type Product } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

const POLL_MS = 1500;

/**
 * Between the brief and the plan.
 *
 * Pressing Start search created the brief and told the backend to read the
 * product website. This screen watches that happen, shows what came back,
 * and only then moves on.
 *
 * It never blocks. A site that fails or has nothing readable still lets the
 * search continue, because a missing product document is a worse result,
 * not a broken one.
 */
export default function ReadingWebsiteRoute() {
  const { productId } = useParams();
  const navigate = useNavigate();

  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Product | null>(null);
  const [continuing, setContinuing] = useState(false);

  const timer = useRef<number | undefined>(undefined);

  const poll = useCallback(async () => {
    if (!productId) return;
    try {
      const next = await productApi.get(productId);
      setProduct(next);
      if (isRunning(next)) {
        timer.current = window.setTimeout(() => void poll(), POLL_MS);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error.");
    }
  }, [productId]);

  useEffect(() => {
    void poll();
    return () => window.clearTimeout(timer.current);
  }, [poll]);

  /* Straight to the marketing plan.
     The planner has usually already written it in the background by the time
     the crawl reports ready, so this is normally instant. When it has not,
     the plan screen shows it being written rather than an empty page. */
  const carryOn = () => {
    setContinuing(true);
    navigate(`/products/${productId}/plan`, { replace: true });
  };

  if (error) {
    return (
      <Box sx={{ maxWidth: 720, mx: "auto", px: 2, py: 7 }}>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Box>
    );
  }

  if (!product) {
    return (
      <Box sx={{ maxWidth: 720, mx: "auto", px: 2, py: 7 }}>
        <Loading label="Opening" />
      </Box>
    );
  }

  const running = isRunning(product);
  const good = product.state === "ready";

  return (
    <Box sx={{ maxWidth: 720, mx: "auto", px: 2, py: { xs: 4, md: 6 } }}>
      <PageHeader
        eyebrow="Step 1 of 3"
        title={running ? `Reading ${product.domain}` : `Read ${product.domain}`}
      >
        {running
          ? "We are reading the product website so the search knows what you sell. This takes anywhere from ten seconds to a few minutes."
          : "This is what we learned about your product. It is stored, and never read again unless you ask."}
      </PageHeader>

      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        {running && <LinearProgress />}

        <Stack sx={{ p: 2.5 }} spacing={1.5}>
          <Stack direction="row" alignItems="center" spacing={1.25} flexWrap="wrap">
            {good && <CheckCircleIcon sx={{ fontSize: 19, color: "success.main" }} />}
            <Typography sx={{ fontWeight: 650, fontSize: 16 }}>{product.name}</Typography>
            {product.mode && (
              <Chip
                size="small"
                variant="outlined"
                label={product.mode === "docs" ? "documentation" : "main pages"}
              />
            )}
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {product.state === "queued" && "Queued. Starting in a moment."}
            {product.state === "crawling" &&
              (product.mode === "docs"
                ? `Found documentation at ${product.docsRoot}. Reading it now.`
                : "Looking for documentation, then reading the most informative pages.")}
            {product.state === "ready" &&
              (product.mode === "docs"
                ? `Read the documentation at ${product.docsRoot}.`
                : "No documentation on this site, so the most informative pages were read instead.")}
          </Typography>
        </Stack>

        {product.failureReason && (
          <Box sx={{ px: 2.5, pb: 2 }}>
            <Alert severity={product.state === "failed" ? "warning" : "info"} variant="outlined">
              {product.failureReason}
            </Alert>
          </Box>
        )}

        {product.truncated && (
          <Box sx={{ px: 2.5, pb: 2 }}>
            <Alert severity="info" variant="outlined">
              {product.stopReason}.
            </Alert>
          </Box>
        )}

        {!running && (
          <>
            <Divider />
            <Stack direction="row" spacing={4} sx={{ px: 2.5, py: 2, flexWrap: "wrap", gap: 2 }}>
              {[
                ["Pages read", String(product.pageCount)],
                ["Words", product.wordCount.toLocaleString()],
                ["Document", `${((product.wordCount * 6) / 1000).toFixed(0)} KB`],
              ].map(([label, value]) => (
                <Box key={label}>
                  <Typography
                    variant="overline"
                    color="text.secondary"
                    sx={{ fontSize: 9.5, letterSpacing: ".12em", display: "block" }}
                  >
                    {label}
                  </Typography>
                  <Typography sx={{ fontFamily: MONO, fontSize: 15, fontWeight: 600 }}>
                    {value}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </>
        )}
      </Paper>

      <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 3, flexWrap: "wrap", gap: 1.5 }}>
        <Button
          variant="contained"
          size="large"
          onClick={carryOn}
          disabled={running || continuing}
        >
          {continuing ? "Working…" : running ? "Waiting for the website…" : "Continue"}
        </Button>

        {good && (
          <Button onClick={() => setViewing(product)}>Read what we found</Button>
        )}

        {/* Always available. A crawl can die with the server and sit on
            "crawling" forever, and nobody should be trapped on this screen. */}
        {running && (
          <Button color="inherit" onClick={carryOn} disabled={continuing}>
            Skip and carry on
          </Button>
        )}

        {!running && !good && (
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: "40ch" }}>
            The search still works without it. Results will just be a little less
            accurate about what fits your product.
          </Typography>
        )}
      </Stack>

      <MarkdownDialog product={viewing} onClose={() => setViewing(null)} />
    </Box>
  );
}
