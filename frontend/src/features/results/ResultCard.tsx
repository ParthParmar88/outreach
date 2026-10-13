import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import LaunchIcon from "@mui/icons-material/Launch";
import ThumbDownOutlinedIcon from "@mui/icons-material/ThumbDownOutlined";

import { percent, SOURCE_LABEL, timeAgo } from "@/lib/format";
import { MONO } from "@/styles/theme";
import { BAND_LABEL, type Band, type RunResult } from "@/lib/types";

const BAND_COLOR: Record<Band, "error" | "warning" | "info" | "default"> = {
  "very-high": "error",
  high: "warning",
  medium: "info",
  weak: "default",
};

interface Props {
  result: RunResult;
  onExplain: (result: RunResult) => void;
  onDraft: (result: RunResult) => void;
  onNotUseful: (result: RunResult) => void;
}

export default function ResultCard({ result, onExplain, onDraft, onNotUseful }: Props) {
  const { conversation: c } = result;
  const dismissed = result.feedback === "not-useful";

  return (
    <Paper variant="outlined" sx={{ overflow: "hidden", opacity: dismissed ? 0.5 : 1 }}>
      <Stack direction="row" spacing={2} sx={{ p: 2, pb: 1.5 }}>
        <Stack alignItems="center" sx={{ minWidth: 62, pr: 2, borderRight: 1, borderColor: "divider" }}>
          <Typography
            sx={{ fontFamily: MONO, fontSize: 26, fontWeight: 650, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}
          >
            {result.score}
          </Typography>
          <Chip
            size="small"
            label={BAND_LABEL[result.band]}
            color={BAND_COLOR[result.band]}
            variant="outlined"
            sx={{ mt: 1, height: 18, fontSize: 10 }}
          />
        </Stack>

        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Link
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
            color="text.primary"
            sx={{ display: "block", fontWeight: 620, fontSize: 15.5, lineHeight: 1.35 }}
          >
            {c.title}
          </Link>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            {SOURCE_LABEL[c.source]} · @{c.author} · {timeAgo(c.createdAt)} · {c.engagement}
          </Typography>
        </Box>
      </Stack>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        divider={<Divider orientation="vertical" flexItem />}
        sx={{ borderTop: 1, borderColor: "divider" }}
      >
        <Box sx={{ p: 1.75, flex: 2, minWidth: 0 }}>
          <Typography variant="overline" color="text.secondary" sx={{ fontSize: 9.5, letterSpacing: ".12em" }}>
            Their problem
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.25 }}>
            {result.problem}
          </Typography>
        </Box>
        <Box sx={{ p: 1.75, flex: 1 }}>
          <Typography variant="overline" color="text.secondary" sx={{ fontSize: 9.5, letterSpacing: ".12em" }}>
            Product fit
          </Typography>
          <Typography sx={{ mt: 0.25, fontWeight: 650, fontSize: 16 }}>
            {percent(result.productFit)}
          </Typography>
        </Box>
        <Box sx={{ p: 1.75, flex: 1 }}>
          <Typography variant="overline" color="text.secondary" sx={{ fontSize: 9.5, letterSpacing: ".12em" }}>
            Actively looking
          </Typography>
          <Typography sx={{ mt: 0.25, fontWeight: 650, fontSize: 16 }}>
            {result.activelyLooking ? "Yes" : "No"}
          </Typography>
        </Box>
      </Stack>

      <Box sx={{ px: 2, py: 1.75, bgcolor: "action.hover", borderTop: 1, borderColor: "divider" }}>
        <Typography variant="overline" color="text.secondary" sx={{ fontSize: 9.5, letterSpacing: ".12em" }}>
          Evidence · their words, not ours
        </Typography>
        <Typography variant="body2" sx={{ mt: 0.5, fontStyle: "italic" }}>
          “{result.evidenceQuote}”
        </Typography>
      </Box>

      <Stack direction="row" spacing={1} sx={{ p: 1.5, borderTop: 1, borderColor: "divider", flexWrap: "wrap", gap: 1 }}>
        <Button
          size="small"
          variant="outlined"
          endIcon={<LaunchIcon sx={{ fontSize: 14 }} />}
          href={c.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open on {SOURCE_LABEL[c.source]}
        </Button>
        <Button size="small" onClick={() => onExplain(result)}>
          Why this score
        </Button>
        <Button size="small" onClick={() => onDraft(result)}>
          Draft a reply
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Teaches the ranking. Costs you one click.">
          <span>
            <Button
              size="small"
              color="inherit"
              startIcon={<ThumbDownOutlinedIcon sx={{ fontSize: 15 }} />}
              disabled={dismissed}
              onClick={() => onNotUseful(result)}
            >
              {dismissed ? "Marked not useful" : "Not useful"}
            </Button>
          </span>
        </Tooltip>
      </Stack>
    </Paper>
  );
}
