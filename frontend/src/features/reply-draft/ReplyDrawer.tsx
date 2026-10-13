import { useEffect, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import { ErrorBlock, Loading } from "@/components/StateBlocks";
import { api } from "@/lib/client";
import type { RunResult } from "@/lib/types";

/**
 * Two permanent rules live in this component.
 *
 *   1. It only runs when the user clicks. Never for every result. Drafting
 *      twenty would add about forty seconds to every run for drafts nobody
 *      reads.
 *   2. There is a Copy button and nothing else. The system never posts.
 *      A person edits and posts under their own name.
 */
export default function ReplyDrawer({
  result,
  onClose,
}: {
  result: RunResult | null;
  onClose: () => void;
}) {
  const [allowMention, setAllowMention] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .draftReply(result.id, allowMention)
      .then((draft) => !cancelled && setText(draft.text))
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [result, allowMention]);

  const words = text.trim().split(/\s+/).filter(Boolean).length;

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <Drawer
      anchor="right"
      open={Boolean(result)}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: "100%", sm: 520 } } } }}
    >
      {result && (
        <Stack sx={{ height: "100%" }}>
          <Box sx={{ p: 2.5, pb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Suggested reply
            </Typography>
            <Typography sx={{ fontWeight: 620, fontSize: 15.5, mt: 0.5 }}>
              {result.conversation.title}
            </Typography>
          </Box>
          <Divider />

          <Box sx={{ p: 2.5, flex: 1, overflowY: "auto" }}>
            {loading ? (
              <Loading label="Writing a reply" />
            ) : error ? (
              <ErrorBlock message={error} />
            ) : (
              <Stack spacing={2}>
                <TextField
                  multiline
                  minRows={12}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  helperText={`${words} words. Edit it before posting. It should sound like you, not like us.`}
                />

                <FormControlLabel
                  control={
                    <Switch
                      size="small"
                      checked={allowMention}
                      onChange={(e) => setAllowMention(e.target.checked)}
                    />
                  }
                  label={<Typography variant="body2">Include a mention of your product</Typography>}
                />

                {allowMention && (
                  <Alert severity="warning" variant="outlined">
                    A mention has to be earned. Help first, name the mechanism rather than
                    the brand, say you built it, and state the honest limit in the same
                    comment.
                  </Alert>
                )}

                <Alert severity="info" variant="outlined">
                  This system never posts. Copy the text and paste it yourself, so a
                  person decides what appears under their own name.
                </Alert>
              </Stack>
            )}
          </Box>

          <Divider />
          <Stack direction="row" spacing={1} sx={{ p: 2 }}>
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
          </Stack>
        </Stack>
      )}
    </Drawer>
  );
}
