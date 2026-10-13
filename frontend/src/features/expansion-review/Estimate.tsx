import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { money, shortHash, SOURCE_LABEL } from "@/lib/format";
import { MONO } from "@/styles/theme";
import type { SearchPlan } from "@/lib/types";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.75 }}>
      <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: MONO, fontSize: 12.5 }}>
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * The plan is frozen and content hashed, so its cost is knowable before it
 * runs. Showing that up front is what makes the approve button honest.
 */
export default function Estimate({ plan }: { plan: SearchPlan }) {
  const p = plan.predicates;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
        What this plan will do
      </Typography>

      <Box>
        <Row label="Documents expected" value={plan.estimatedDocuments.toLocaleString()} />
        <Row label="Estimated cost" value={money(plan.estimatedCostUsd)} />
        <Row label="Stages" value={String(plan.stages.length)} />
      </Box>

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Filters applied before any scoring
      </Typography>
      <Box>
        <Row label="Sources" value={p.sources.map((s) => SOURCE_LABEL[s]).join(", ")} />
        <Row label="Date window" value={`${p.dateFrom} → ${p.dateTo}`} />
        <Row label="Language" value={p.language} />
        <Row label="Minimum engagement" value={String(p.minEngagement)} />
        <Row label="Excluded" value={p.excludedTerms.join(", ") || "none"} />
      </Box>

      <Divider sx={{ my: 1.5 }} />

      <Row label={`Plan hash · v${plan.version}`} value={shortHash(plan.planHash)} />
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        Two identical plans have the same hash and cost the same to run.
      </Typography>
    </Paper>
  );
}
