import { useState } from "react";

import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import ReplyDrawer from "@/features/reply-draft/ReplyDrawer";
import { api } from "@/lib/client";
import type { RunResult } from "@/lib/types";
import ResultCard from "./ResultCard";
import ScoreBreakdown from "./ScoreBreakdown";

interface Props {
  results: RunResult[];
  /** Shown under the list while the run is still going. */
  streaming?: boolean;
}

export default function ResultList({ results, streaming = false }: Props) {
  const [local, setLocal] = useState<Record<string, "not-useful">>({});
  const [explain, setExplain] = useState<RunResult | null>(null);
  const [draft, setDraft] = useState<RunResult | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const decorated = results.map((r) =>
    local[r.id] ? { ...r, feedback: local[r.id] } : r,
  );

  const strong = decorated.filter((r) => r.band !== "weak");
  const weak = decorated.filter((r) => r.band === "weak");

  const markNotUseful = async (result: RunResult) => {
    setLocal((prev) => ({ ...prev, [result.id]: "not-useful" }));
    setToast("Noted. That teaches the ranking.");
    try {
      await api.sendFeedback(result.id, "not-useful");
    } catch {
      setToast("Could not save that. It will be lost on refresh.");
    }
  };

  return (
    <>
      <Stack spacing={2}>
        {strong.map((result) => (
          <ResultCard
            key={result.id}
            result={result}
            onExplain={setExplain}
            onDraft={setDraft}
            onNotUseful={markNotUseful}
          />
        ))}
      </Stack>

      {streaming && strong.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          More arriving…
        </Typography>
      )}

      {/* Weak matches are collapsed, never dropped and never used to pad the list. */}
      {weak.length > 0 && (
        <Accordion variant="outlined" disableGutters sx={{ mt: 3 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" color="text.secondary">
              {weak.length} weak match{weak.length === 1 ? "" : "es"} · scored under 32
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              {weak.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  onExplain={setExplain}
                  onDraft={setDraft}
                  onNotUseful={markNotUseful}
                />
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}

      <ScoreBreakdown result={explain} onClose={() => setExplain(null)} />
      <ReplyDrawer result={draft} onClose={() => setDraft(null)} />

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={2600}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </>
  );
}
