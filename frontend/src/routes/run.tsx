import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Box from "@mui/material/Box";

import { ErrorBlock, Loading, PageHeader } from "@/components/StateBlocks";
import ResultList from "@/features/results/ResultList";
import StageList from "@/features/run-progress/StageList";
import { useRunStream } from "@/features/run-progress/useRunStream";

/**
 * A run in flight.
 *
 * Results appear underneath the stages as they land rather than all at the
 * end, so the first one is on screen in a few seconds. When the run
 * succeeds the route is replaced with the permanent results page.
 */
export default function RunRoute() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { run, results, error, transport } = useRunStream(runId);

  useEffect(() => {
    if (run?.state === "succeeded") {
      navigate(`/runs/${run.id}/results`, { replace: true });
    }
  }, [run, navigate]);

  if (error && !run) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Box>
    );
  }

  if (!run) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <Loading label="Opening the run" />
      </Box>
    );
  }

  if (run.state === "failed") {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <ErrorBlock
          message={run.error ?? "The run stopped before it finished."}
          onRetry={() => navigate("/new")}
        />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: { xs: 3, md: 5 } }}>
      <PageHeader eyebrow="Running" title="Working on it" />

      <Box sx={{ mb: 3 }}>
        <StageList run={run} transport={transport} />
      </Box>

      <ResultList results={results} streaming />
    </Box>
  );
}
