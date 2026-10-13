import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";

import { money } from "@/lib/format";
import type { SearchRun, StageProgress } from "@/lib/types";

function Icon({ state }: { state: StageProgress["state"] }) {
  if (state === "done") return <CheckCircleIcon sx={{ fontSize: 16, color: "success.main" }} />;
  if (state === "running") return <CircularProgress size={13} sx={{ mx: "1.5px" }} />;
  if (state === "skipped")
    return <RemoveCircleOutlineIcon sx={{ fontSize: 16, color: "text.disabled" }} />;
  return <RadioButtonUncheckedIcon sx={{ fontSize: 16, color: "text.disabled" }} />;
}

/**
 * The fourteen stages from the plan, in order. Never a bare spinner: the
 * user is told which stage is running, what it produced, and what it has
 * cost so far.
 */
export default function StageList({
  run,
  transport,
}: {
  run: SearchRun;
  transport: "sse" | "polling";
}) {
  return (
    <Paper variant="outlined" sx={{ overflow: "hidden" }}>
      <Box sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Typography variant="subtitle2" sx={{ flex: 1 }}>
            {run.state === "succeeded" ? "Run finished" : "Running"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {run.callsUsed} / {run.callBudget} calls · {money(run.costUsd)}
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={run.percent}
          sx={{ mt: 1.25, height: 5, borderRadius: 3 }}
        />
        {transport === "polling" && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
            Live updates unavailable, checking every second instead.
          </Typography>
        )}
      </Box>

      <Stack sx={{ px: 2, py: 1 }}>
        {run.stages.map((stage) => (
          <Stack key={stage.id} direction="row" alignItems="center" spacing={1.25} sx={{ py: 0.6 }}>
            <Icon state={stage.state} />
            <Typography
              variant="body2"
              sx={{
                flex: 1,
                color: stage.state === "waiting" ? "text.disabled" : "text.primary",
                fontWeight: stage.state === "running" ? 620 : 400,
              }}
            >
              {stage.label}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {stage.state === "waiting" ? "" : stage.detail}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
