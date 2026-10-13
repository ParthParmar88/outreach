import { useEffect, useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";

import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import { ErrorBlock, Loading } from "@/components/StateBlocks";
import { productApi, type Product } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

interface Props {
  product: Product | null;
  onClose: () => void;
}

/**
 * The stored document, and the pages it came from.
 *
 * This is the file that later gets handed to the model. Being able to read
 * it is the whole point: if it looks wrong here, no amount of clever
 * scoring downstream will fix it.
 */
export default function MarkdownDialog({ product, onClose }: Props) {
  const [tab, setTab] = useState(0);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [detail, setDetail] = useState<Product | null>(null);

  useEffect(() => {
    if (!product) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTab(0);

    Promise.all([productApi.markdown(product.id), productApi.get(product.id)])
      .then(([markdown, full]) => {
        if (cancelled) return;
        setText(markdown);
        setDetail(full);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error.");
      })
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [product]);

  if (!product) return null;

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const pages = detail?.pages ?? [];

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 0 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              What we read from {product.domain}
            </Typography>
            <Typography sx={{ fontWeight: 650, fontSize: 17 }}>{product.name}</Typography>
          </Box>
          <Chip
            size="small"
            variant="outlined"
            label={`${(text.length / 1000).toFixed(0)} KB`}
          />
        </Stack>
        <Tabs value={tab} onChange={(_, v: number) => setTab(v)}>
          <Tab label="The document" />
          <Tab label={`Pages (${pages.length})`} />
        </Tabs>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 0 }}>
        {loading ? (
          <Loading label="Loading the document" />
        ) : error ? (
          <Box sx={{ p: 3 }}>
            <ErrorBlock message={error} />
          </Box>
        ) : tab === 0 ? (
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2.5,
              fontFamily: MONO,
              fontSize: 12.5,
              lineHeight: 1.7,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              maxHeight: "60vh",
              overflowY: "auto",
              bgcolor: "background.default",
            }}
          >
            {text}
          </Box>
        ) : (
          <Box sx={{ maxHeight: "60vh", overflowY: "auto" }}>
            {pages.map((page) => (
              <Stack
                key={page.id}
                direction="row"
                spacing={2}
                alignItems="baseline"
                sx={{ px: 2.5, py: 1.25, borderBottom: 1, borderColor: "divider" }}
              >
                <Typography
                  sx={{ fontFamily: MONO, fontSize: 12.5, minWidth: 62, textAlign: "right" }}
                  color={page.isThin ? "text.disabled" : "text.primary"}
                >
                  {page.wordCount.toLocaleString()}w
                </Typography>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 560 }}>
                    {page.title || "(no title)"}
                    {page.isThin && (
                      <Chip
                        size="small"
                        label="empty"
                        variant="outlined"
                        sx={{ ml: 1, height: 17, fontSize: 9.5 }}
                      />
                    )}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontFamily: MONO, wordBreak: "break-all" }}
                  >
                    {page.url}
                  </Typography>
                </Box>
              </Stack>
            ))}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Button
          size="small"
          startIcon={<OpenInNewIcon sx={{ fontSize: 16 }} />}
          href={productApi.markdownUrl(product.id)}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open raw
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="contained"
          startIcon={<ContentCopyIcon sx={{ fontSize: 16 }} />}
          onClick={copy}
          disabled={loading || Boolean(error)}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
