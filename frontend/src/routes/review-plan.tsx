import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { ErrorBlock, Loading, PageHeader } from "@/components/StateBlocks";
import ChipGrid from "@/features/expansion-review/ChipGrid";
import Estimate from "@/features/expansion-review/Estimate";
import ExamplePosts from "@/features/expansion-review/ExamplePosts";
import { api } from "@/lib/client";
import type { PlanTerm, SearchPlan } from "@/lib/types";

/**
 * Expansion review: chips with origin, example posts, live estimate.
 *
 * The one LLM call has already happened and its output is frozen into the
 * plan. This screen exists so the user can see and edit that output before
 * anything is spent on a run.
 */
export default function ReviewPlanRoute() {
  const { planId } = useParams();
  const navigate = useNavigate();

  const [plan, setPlan] = useState<SearchPlan | null>(null);
  const [terms, setTerms] = useState<PlanTerm[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    api
      .getPlan(planId)
      .then((p) => {
        if (cancelled) return;
        setPlan(p);
        setTerms(p.terms);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error.");
      });
    return () => {
      cancelled = true;
    };
  }, [planId]);

  const start = async () => {
    if (!plan) return;
    setStarting(true);
    setError(null);
    try {
      const changed =
        terms.length !== plan.terms.length ||
        terms.some((t, i) => t.term !== plan.terms[i]?.term);

      // Editing the terms produces a new plan version with a new hash.
      const finalPlan = changed
        ? await api.amendPlan(plan.id, terms.map((t) => t.term))
        : plan;

      const run = await api.startRun(finalPlan.id);
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error.");
      setStarting(false);
    }
  };

  if (error && !plan) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Box>
    );
  }

  if (!plan) {
    return (
      <Box sx={{ maxWidth: 860, mx: "auto", px: 2, py: 7 }}>
        <Loading label="Compiling the plan" />
      </Box>
    );
  }

  const added = terms.filter((t) => t.origin === "expansion").length;

  return (
    <Box sx={{ maxWidth: 980, mx: "auto", px: 2, py: { xs: 4, md: 6 } }}>
      <PageHeader eyebrow="Review the plan · nothing spent yet" title="Check this before it runs">
        The compiler added {added} terms to the ones you gave it. Delete anything that
        looks wrong. Below are three posts of the kind this plan will look for, written
        out in full.
      </PageHeader>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error} Nothing was spent.
        </Alert>
      )}

      <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Paper variant="outlined" sx={{ p: { xs: 2.5, md: 3 }, mb: 3 }}>
            <Typography variant="subtitle2" sx={{ mb: 2 }}>
              Terms this plan will execute
            </Typography>
            <ChipGrid terms={terms} onChange={setTerms} />
          </Paper>

          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Posts like these
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "60ch" }}>
            If these are not the conversations you meant, go back and change the
            description. That field matters more than the terms.
          </Typography>
          <ExamplePosts posts={plan.examplePosts} />
        </Box>

        <Box sx={{ width: { xs: "100%", md: 320 }, flexShrink: 0 }}>
          <Estimate plan={{ ...plan, terms }} />
        </Box>
      </Stack>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }} sx={{ mt: 4 }}>
        <Button variant="contained" size="large" onClick={start} disabled={starting || terms.length === 0}>
          {starting ? "Starting…" : "Looks right, run it"}
        </Button>
        <Button color="inherit" onClick={() => navigate("/new")}>
          Back and change the brief
        </Button>
      </Stack>
    </Box>
  );
}
