import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { Surface } from "@/components/ui";

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import RefreshIcon from "@mui/icons-material/Refresh";

import { MONO } from "@/styles/theme";
import { isRunning, type CrawlState, type Product } from "@/lib/productApi";

const STATE: Record<
  CrawlState,
  { label: string; color: "default" | "info" | "success" | "warning" | "error"; note?: string }
> = {
  queued: { label: "Queued", color: "info", note: "Registered. The crawl is about to start." },
  crawling: { label: "Reading the site", color: "info" },
  ready: { label: "Ready", color: "success" },
  thin: {
    label: "Nothing readable",
    color: "warning",
    note: "Either the site renders with JavaScript, which plain fetching cannot see, or there is genuinely very little text on it.",
  },
  failed: { label: "Failed", color: "error" },
};

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ minWidth: 92 }}>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ fontSize: 9.5, letterSpacing: ".12em", display: "block" }}
      >
        {label}
      </Typography>
      <Typography sx={{ fontFamily: MONO, fontSize: 14, fontWeight: 600 }}>{value}</Typography>
    </Box>
  );
}

interface Props {
  product: Product;
  onView: (product: Product) => void;
  onRecrawl: (product: Product) => void;
  onDelete: (product: Product) => void;
  busy: boolean;
}

export default function ProductCard({ product, onView, onRecrawl, onDelete, busy }: Props) {
  const state = STATE[product.state];
  const running = isRunning(product);

  return (
    <Surface interactive sx={{ overflow: "hidden" }}>
      {running && <LinearProgress />}

      <Stack sx={{ p: 2.25, pb: 1.75 }} spacing={0.75}>
        <Stack direction="row" alignItems="center" spacing={1.25} flexWrap="wrap">
          <Typography sx={{ fontWeight: 650, fontSize: 16 }}>{product.name}</Typography>
          <Chip size="small" label={state.label} color={state.color} variant="outlined" />
          {product.mode && (
            <Tooltip
              title={
                product.mode === "docs"
                  ? "The site has documentation, so only the documentation was read."
                  : "No documentation found, so the most informative pages were read instead."
              }
            >
              <Chip
                size="small"
                label={product.mode === "docs" ? "docs only" : "main pages"}
                variant="outlined"
              />
            </Tooltip>
          )}
        </Stack>

        <Link
          href={product.canonicalUrl}
          target="_blank"
          rel="noopener noreferrer"
          variant="caption"
          color="text.secondary"
          underline="hover"
        >
          {product.canonicalUrl}
        </Link>

        {product.docsRoot && (
          <Typography variant="caption" color="text.secondary">
            Documentation at{" "}
            <Box component="span" sx={{ fontFamily: MONO }}>
              {product.docsRoot}
            </Box>
          </Typography>
        )}
      </Stack>

      {state.note && product.state !== "ready" && (
        <Box sx={{ px: 2.25, pb: 1.5 }}>
          <Typography variant="body2" color="text.secondary">
            {state.note}
          </Typography>
        </Box>
      )}

      {product.failureReason && (
        <Box sx={{ px: 2.25, pb: 1.5 }}>
          <Alert severity={product.state === "failed" ? "error" : "warning"} variant="outlined">
            {product.failureReason}
          </Alert>
        </Box>
      )}

      {product.truncated && (
        <Box sx={{ px: 2.25, pb: 1.5 }}>
          <Alert severity="info" variant="outlined">
            {product.stopReason}. We are telling you rather than pretending the whole
            site was read.
          </Alert>
        </Box>
      )}

      <Divider />

      <Stack direction="row" spacing={3} sx={{ px: 2.25, py: 1.75, flexWrap: "wrap", gap: 2 }}>
        <Fact label="Pages" value={String(product.pageCount)} />
        <Fact label="Words" value={product.wordCount.toLocaleString()} />
        <Fact label="Downloaded" value={`${(product.bytesFetched / 1_000_000).toFixed(1)} MB`} />
        {product.contentHash && (
          <Fact label="Fingerprint" value={product.contentHash.slice(0, 8)} />
        )}
      </Stack>

      <Divider />

      <Stack direction="row" spacing={1} sx={{ p: 1.5, flexWrap: "wrap", gap: 1 }}>
        <Button
          size="small"
          variant="contained"
          startIcon={<ArticleOutlinedIcon sx={{ fontSize: 17 }} />}
          onClick={() => onView(product)}
          disabled={product.state !== "ready"}
        >
          Read the document
        </Button>
        {/* Neither of these is disabled while running, on purpose. A crawl
            that died with the server still says "crawling", and a row you
            cannot restart or remove is a row stuck forever. The backend
            decides: it answers 409 if the crawl is genuinely alive. */}
        <Button
          size="small"
          startIcon={<RefreshIcon sx={{ fontSize: 17 }} />}
          onClick={() => onRecrawl(product)}
          disabled={busy}
        >
          Read again
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Removes the product and every page we stored for it">
          <span>
            <Button
              size="small"
              color="error"
              startIcon={<DeleteOutlineIcon sx={{ fontSize: 17 }} />}
              onClick={() => onDelete(product)}
              disabled={busy}
            >
              Delete
            </Button>
          </span>
        </Tooltip>
      </Stack>
    </Surface>
  );
}
