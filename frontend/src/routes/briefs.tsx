import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ReplayIcon from "@mui/icons-material/Replay";

import { ErrorBlock, Loading, PageHeader } from "@/components/StateBlocks";
import { SOURCE_LABEL, timeAgo } from "@/lib/format";
import { api } from "@/lib/client";
import type { Brief, RunState } from "@/lib/types";

const RUN_STATE: Record<RunState, { label: string; color: "default" | "warning" | "success" | "error" }> = {
  queued: { label: "Queued", color: "warning" },
  running: { label: "Running", color: "warning" },
  succeeded: { label: "Done", color: "success" },
  failed: { label: "Failed", color: "error" },
  cancelled: { label: "Cancelled", color: "default" },
};

/**
 * Saved briefs.
 *
 * This screen is the reason a form beat a chatbot. A saved brief can be
 * recompiled and run again on a schedule and show only what is new. A chat
 * message cannot.
 */
export default function BriefsRoute() {
  const navigate = useNavigate();
  const [briefs, setBriefs] = useState<Brief[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listBriefs()
      .then((list) => !cancelled && setBriefs(list))
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rerun = async (brief: Brief) => {
    setBusyId(brief.id);
    try {
      const plan = await api.compilePlan(brief.id);
      navigate(`/plans/${plan.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error.");
      setBusyId(null);
    }
  };

  return (
    <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: { xs: 4, md: 6 } }}>
      <PageHeader
        eyebrow="Saved"
        title="Your briefs"
        action={
          <Button component={RouterLink} to="/new" variant="contained">
            New search
          </Button>
        }
      />

      {error && <ErrorBlock message={error} />}
      {!error && !briefs && <Loading label="Loading your briefs" />}

      {briefs?.length === 0 && (
        <Paper variant="outlined" sx={{ p: 5, textAlign: "center" }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            No briefs yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "42ch", mx: "auto", mb: 3 }}>
            Describe what you are looking for and we keep the brief here, so you can run
            it again whenever you want.
          </Typography>
          <Button component={RouterLink} to="/new" variant="outlined">
            Write the first one
          </Button>
        </Paper>
      )}

      <Stack spacing={1.5}>
        {briefs?.map((brief) => (
          <Paper key={brief.id} variant="outlined" sx={{ p: 2.25 }}>
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.75 }}>
              {brief.latestRunState && (
                <Chip
                  size="small"
                  label={RUN_STATE[brief.latestRunState].label}
                  color={RUN_STATE[brief.latestRunState].color}
                  variant="outlined"
                />
              )}
              <Typography variant="caption" color="text.secondary">
                {brief.productName} · {timeAgo(brief.createdAt)}
              </Typography>
              <Box sx={{ flexGrow: 1 }} />
              {typeof brief.resultCount === "number" && (
                <Typography variant="caption" color="text.secondary">
                  {brief.resultCount} result{brief.resultCount === 1 ? "" : "s"}
                </Typography>
              )}
            </Stack>

            <Typography variant="body2" sx={{ mb: 1 }}>
              {brief.description}
            </Typography>

            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                {brief.sources.map((s) => SOURCE_LABEL[s]).join(" · ")} · last{" "}
                {brief.daysBack} days
              </Typography>

              {brief.latestRunId && (
                <Button size="small" component={RouterLink} to={`/runs/${brief.latestRunId}/results`}>
                  Open results
                </Button>
              )}
              <Button
                size="small"
                variant="outlined"
                startIcon={<ReplayIcon sx={{ fontSize: 16 }} />}
                onClick={() => rerun(brief)}
                disabled={busyId === brief.id}
              >
                {busyId === brief.id ? "Compiling…" : "Run again"}
              </Button>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}
