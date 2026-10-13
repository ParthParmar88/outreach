import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { MONO } from "@/styles/theme";
import type { RunResult } from "@/lib/types";

const num = { fontFamily: MONO, fontVariantNumeric: "tabular-nums" } as const;

/**
 * A marketer is about to post a public comment under their own name. They
 * will not act on a number they cannot question, so every point is shown,
 * and the multiplier is shown as a multiplier.
 */
export default function ScoreBreakdown({
  result,
  onClose,
}: {
  result: RunResult | null;
  onClose: () => void;
}) {
  if (!result) return null;
  const d = result.scoreDetail;

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Typography variant="subtitle2" color="text.secondary">
          Why this scored {result.score}
        </Typography>
        <Typography sx={{ fontWeight: 620, fontSize: 16, mt: 0.5 }}>
          {result.conversation.title}
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2}>
          {d.components.map((c) => (
            <Box key={c.name}>
              <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mb: 0.5 }}>
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {c.name}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={num}>
                  {c.raw.toFixed(2)} × {c.weight.toFixed(2)}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ ...num, fontWeight: 650, minWidth: 46, textAlign: "right" }}
                >
                  {c.points.toFixed(2)}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={c.raw * 100}
                sx={{ height: 5, borderRadius: 3 }}
              />
            </Box>
          ))}

          <Stack direction="row" sx={{ pt: 1, borderTop: 1, borderColor: "divider" }}>
            <Typography variant="body2" sx={{ flex: 1 }}>
              Subtotal
            </Typography>
            <Typography variant="body2" sx={{ ...num, fontWeight: 650 }}>
              {d.subtotal.toFixed(2)}
            </Typography>
          </Stack>

          <Stack direction="row">
            <Typography variant="body2" sx={{ flex: 1 }}>
              Relevance <b>multiplier</b>
            </Typography>
            <Typography variant="body2" sx={{ ...num, fontWeight: 650 }}>
              × {d.relevance.toFixed(2)}
            </Typography>
          </Stack>

          <Stack direction="row" alignItems="center" sx={{ pt: 1.5, borderTop: 1, borderColor: "divider" }}>
            <Typography sx={{ flex: 1, fontWeight: 650 }}>Final</Typography>
            <Typography sx={{ ...num, fontWeight: 700, fontSize: 22 }}>{d.final}</Typography>
          </Stack>

          {d.relevance < 0.2 && (
            <Alert severity="info" variant="outlined">
              This is the multiplier doing its job. The five components add up to{" "}
              <b>{d.subtotal.toFixed(0)}</b> because the post is recent and popular, but
              it has nothing to do with what you sell. A relevance of{" "}
              {d.relevance.toFixed(2)} takes it to {d.final}. If relevance were a sixth
              weighted component instead, this would have scored around 67 and sat on
              your first page.
            </Alert>
          )}
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
