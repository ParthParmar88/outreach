import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";

import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";

import { ErrorBlock, Loading, PageHeader } from "@/components/StateBlocks";
import EmptyState from "@/features/results/EmptyState";
import ResultList from "@/features/results/ResultList";
import { api } from "@/lib/client";
import type { RunResult } from "@/lib/types";

/**
 * The finished result set. This is the page people link to and come back to,
 * so it does not poll and does not show the stage list.
 */
export default function ResultsRoute() {
  const { runId } = useParams();
  const [results, setResults] = useState<RunResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    api
      .getRunResults(runId)
      .then((r) => !cancelled && setResults(r))
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error.");
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Box>
    );
  }

  if (!results) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <Loading label="Loading results" />
      </Box>
    );
  }

  const shown = results.filter((r) => r.band !== "weak").length;

  return (
    <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: { xs: 3, md: 5 } }}>
      <PageHeader
        eyebrow="Results"
        title={`${shown} worth looking at`}
        action={
          results.length > 0 && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<FileDownloadOutlinedIcon sx={{ fontSize: 17 }} />}
              href={api.exportUrl(runId!)}
            >
              Export
            </Button>
          )
        }
      />

      {results.length === 0 ? <EmptyState /> : <ResultList results={results} />}
    </Box>
  );
}
