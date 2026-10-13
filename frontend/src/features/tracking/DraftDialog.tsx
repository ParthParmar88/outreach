import { useEffect, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import CheckIcon from "@mui/icons-material/Check";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import {
  trackingApi,
  type DraftRequest,
  type TrackedPost,
} from "@/lib/trackingApi";
import { MONO } from "@/styles/theme";

interface Props {
  productId: string;
  /** The post to write about. Null closes the dialog. */
  post: DraftRequest | null;
  onClose: () => void;
  /** So the tracking tab can refresh behind the dialog. */
  onSaved?: (tracked: TrackedPost) => void;
}

/**
 * Write a reply, read it, copy it, then say whether you sent it.
 *
 * Deliberately three separate steps rather than one button. The draft is a
 * first attempt at somebody else's conversation, and the moment it is
 * treated as finished text the product starts writing comments in your name
 * that you have not read.
 */
export default function DraftDialog({ productId, post, onClose, onSaved }: Props) {
  const [allowMention, setAllowMention] = useState(true);
  const [tracked, setTracked] = useState<TrackedPost | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [commentUrl, setCommentUrl] = useState("");
  const [saving, setSaving] = useState(false);

  // Reset when a different post opens the dialog, or the previous draft
  // would be sitting there under a new title.
  useEffect(() => {
    setTracked(null);
    setError(null);
    setCopied(false);
    setCommentUrl("");
  }, [post?.source_id]);

  const write = async () => {
    if (!post) return;
    setWriting(true);
    setError(null);
    try {
      const result = await trackingApi.draft(productId, { ...post, allow_mention: allowMention });
      setTracked(result);
      onSaved?.(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWriting(false);
    }
  };

  const copy = async () => {
    if (!tracked?.draft) return;
    try {
      await navigator.clipboard.writeText(tracked.draft);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access is refused in some browsers. The text is on screen
      // and selectable, so this is a missing convenience, not a failure.
      setError("Could not copy automatically — select the text and copy it.");
    }
  };

  const confirmPosted = async () => {
    if (!tracked) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await trackingApi.markPosted(tracked.id, commentUrl.trim() || null);
      setTracked(updated);
      onSaved?.(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const posted = tracked?.state === "posted";

  return (
    <Dialog open={Boolean(post)} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Typography sx={{ fontWeight: 660, fontSize: 18 }}>Reply to this post</Typography>
        {post && (
          <Link
            href={post.url}
            target="_blank"
            rel="noopener"
            underline="hover"
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              fontSize: 13,
              color: "text.secondary",
              mt: 0.5,
            }}
          >
            {post.title}
            <OpenInNewIcon sx={{ fontSize: 13 }} />
          </Link>
        )}
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ pt: 2.5 }}>
        <Stack gap={2.5}>
          {error && <Alert severity="error">{error}</Alert>}

          {/* ------------------------------------------------ before */}
          {!tracked && (
            <>
              <FormControlLabel
                control={
                  <Switch
                    checked={allowMention}
                    onChange={(e) => setAllowMention(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography sx={{ fontSize: 14, fontWeight: 600 }}>
                      May mention your product
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {allowMention
                        ? "One sentence at the end, only if it genuinely bears on what they asked."
                        : "A purely helpful answer. Often the better first move in a repository nobody there has heard of you."}
                    </Typography>
                  </Box>
                }
              />

              <Button
                variant="contained"
                size="large"
                onClick={write}
                disabled={writing}
                startIcon={writing ? <CircularProgress size={16} color="inherit" /> : null}
              >
                {writing ? "Writing…" : "Write the reply"}
              </Button>

              <Typography variant="caption" color="text.secondary">
                Takes about ten seconds. Nothing is posted anywhere — you get
                text to read, and you decide.
              </Typography>
            </>
          )}

          {/* ------------------------------------- the model said don't */}
          {tracked?.skip_reason && (
            <Alert severity="warning" variant="outlined">
              <Typography sx={{ fontWeight: 600, fontSize: 14, mb: 0.5 }}>
                Better not to reply to this one
              </Typography>
              <Typography variant="body2">{tracked.skip_reason}</Typography>
            </Alert>
          )}

          {/* ------------------------------------------------- the draft */}
          {tracked?.draft && (
            <>
              <Box>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 1 }}
                >
                  <Typography
                    variant="overline"
                    sx={{ fontSize: 10, letterSpacing: ".1em", color: "text.secondary" }}
                  >
                    Draft
                  </Typography>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={
                      tracked.draft_mentions_product
                        ? "mentions your product"
                        : "no product mention"
                    }
                    color={tracked.draft_mentions_product ? "default" : "success"}
                    sx={{ height: 20, fontSize: 10.5 }}
                  />
                </Stack>

                <Box
                  sx={{
                    p: 2,
                    borderRadius: 1,
                    border: 1,
                    borderColor: "divider",
                    bgcolor: "action.hover",
                    whiteSpace: "pre-wrap",
                    fontSize: 14,
                    lineHeight: 1.65,
                    maxHeight: 300,
                    overflowY: "auto",
                  }}
                >
                  {tracked.draft}
                </Box>
              </Box>

              <Stack direction="row" gap={1.5} flexWrap="wrap">
                <Button
                  variant="outlined"
                  startIcon={copied ? <CheckIcon /> : <ContentCopyIcon />}
                  onClick={copy}
                  color={copied ? "success" : "primary"}
                >
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button
                  variant="text"
                  endIcon={<OpenInNewIcon />}
                  href={tracked.url}
                  target="_blank"
                  rel="noopener"
                >
                  Open the thread
                </Button>
                <Button onClick={write} disabled={writing}>
                  {writing ? "Rewriting…" : "Write another"}
                </Button>
              </Stack>

              <Divider />

              {/* -------------------------------------- did you post it */}
              {posted ? (
                <Alert severity="success" variant="outlined" icon={<CheckIcon />}>
                  <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
                    Marked as posted
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {tracked.our_comment_url
                      ? "We have your comment link, so a reply check can tell who answered you."
                      : "No comment link, so replies will be counted rather than attributed."}
                  </Typography>
                </Alert>
              ) : (
                <Box>
                  <Typography sx={{ fontWeight: 600, fontSize: 14, mb: 0.5 }}>
                    Did you post it?
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
                    Paste the link to your own comment if you have it. On GitHub,
                    the <b>…</b> menu on your comment has <b>Copy link</b>. Without
                    it we can only count new comments, and a busy issue gets those
                    whether you turned up or not.
                  </Typography>

                  <TextField
                    size="small"
                    fullWidth
                    value={commentUrl}
                    onChange={(e) => setCommentUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo/issues/12#issuecomment-456789"
                    slotProps={{ input: { sx: { fontFamily: MONO, fontSize: 12 } } }}
                    sx={{ mb: 1.5 }}
                  />

                  <Button variant="contained" onClick={confirmPosted} disabled={saving}>
                    {saving ? "Saving…" : "I posted this"}
                  </Button>
                </Box>
              )}
            </>
          )}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
