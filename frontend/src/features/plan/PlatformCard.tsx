import { useState, type ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import SearchIcon from "@mui/icons-material/Search";

import EditableChips from "./EditableChips";
import RepoSuggest from "./RepoSuggest";
import { platformIcon } from "./platformIcon";
import { IconTile, Label, Surface, hairline } from "@/components/ui";
import type { PlanPlatform } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

interface Props {
  platform: PlanPlatform;
  /** Seeds the repository search. The product's domain works well. */
  topic?: string;
  /**
   * The card has the full content width to itself, so it lays out in two
   * columns instead of one tall ribbon. Decided by the group, which is the
   * only place that knows how many cards are sharing the row.
   */
  wide?: boolean;
  onFindOpportunities?: (
    platform: PlanPlatform,
    terms: string[],
    repos: string[],
  ) => void;
}

/** One word matches tens of thousands of issues; GitHub serves 1,000 of them. */
function warnTerm(term: string): string | null {
  const words = term.trim().split(/\s+/).length;
  if (words === 1) return "One word is too broad — you will see a random slice.";
  if (words > 3) return "Too long — matched as an exact phrase, so it will find nothing.";
  return null;
}

/** A label above its text. Used often enough here to be worth a name. */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Label>{label}</Label>
      <Typography variant="body2" sx={{ lineHeight: 1.7, mt: 0.5 }}>
        {children}
      </Typography>
    </Box>
  );
}

/**
 * One platform from the plan.
 *
 * Three states, and keeping them apart is the point of this component.
 * "We can search this now", "we will be able to" and "we never will" are
 * three different promises, and collapsing the last two leaves someone
 * waiting for posts that are not coming.
 */
export default function PlatformCard({
  platform,
  topic,
  wide = false,
  onFindOpportunities,
}: Props) {
  // Local, not saved back to the plan. A tweak for one run should not
  // silently rewrite the agent's plan underneath the user.
  const [terms, setTerms] = useState(platform.searchTerms);
  const [repos, setRepos] = useState(platform.targetPlaces);

  const Icon = platformIcon(platform.key, platform.name);
  const live = platform.availableNow;
  const pending = platform.searchable && !platform.availableNow;

  const status = live
    ? { label: "Ready to search", color: "success" as const }
    : pending
      ? { label: "Connector coming", color: "warning" as const }
      : { label: "By hand", color: "default" as const };

  const header = (
    <Stack direction="row" alignItems="center" gap={1.5}>
      <IconTile tone={live ? "success" : "muted"} size={wide ? 42 : 36}>
        <Icon />
      </IconTile>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{ fontWeight: 690, fontSize: wide ? 19 : 16.5, letterSpacing: "-.015em" }}
          noWrap
        >
          {platform.name}
        </Typography>
        {wide && (
          <Typography variant="caption" color="text.secondary">
            Every recent issue and discussion becomes a candidate
          </Typography>
        )}
      </Box>

      <Chip
        size="small"
        label={status.label}
        color={live ? "success" : status.color}
        variant={live ? "filled" : "outlined"}
        sx={{ height: 23, fontSize: 11, flexShrink: 0, fontWeight: 600 }}
      />
    </Stack>
  );

  /* The story: why here, what to do, in what voice. Kept as separate
     blocks rather than one lump, because a card with the row to itself
     lays them out side by side instead of running one narrow column down
     the left and leaving the other half of the card empty. */
  const blocks: ReactNode[] = [];
  if (platform.why) blocks.push(<Field key="why" label="Why here">{platform.why}</Field>);
  if (platform.whatToDo)
    blocks.push(<Field key="what" label="What to do">{platform.whatToDo}</Field>);
  if (platform.tone) blocks.push(<Field key="tone" label="Tone">{platform.tone}</Field>);
  if (!live && platform.targetPlaces.length > 0) {
    blocks.push(
      <Box key="where">
        <Label>Where</Label>
        <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 0.75 }}>
          {platform.targetPlaces.map((place) => (
            <Chip
              key={place}
              size="small"
              label={place}
              variant="outlined"
              sx={{ fontFamily: MONO, fontSize: 11.5, height: 24 }}
            />
          ))}
        </Stack>
      </Box>,
    );
  }

  const narrative = <Stack gap={2.25}>{blocks}</Stack>;

  /* The controls, on the live card only. */
  const tuning = live ? (
    <Stack gap={2.5}>
      <EditableChips
        label="Repositories to sweep"
        hint="Every recent issue becomes a candidate, no keyword needed. This is your best source."
        values={repos}
        placeholder="owner/name"
        onChange={setRepos}
      />
      <RepoSuggest
        topic={topic || platform.name}
        current={repos}
        onAdd={(name) =>
          setRepos((prev) =>
            prev.some((r) => r.toLowerCase() === name.toLowerCase()) ? prev : [...prev, name],
          )
        }
      />
      <Divider />
      <EditableChips
        label="Phrases to search"
        hint="Two or three words each. One word matches tens of thousands and you only ever see the first 1,000."
        values={terms}
        placeholder="stale index"
        onChange={setTerms}
        warn={warnTerm}
      />
    </Stack>
  ) : null;

  const action = live ? (
    onFindOpportunities && (
      <Button
        variant="contained"
        size="large"
        fullWidth
        startIcon={<SearchIcon />}
        onClick={() => onFindOpportunities(platform, terms, repos)}
        sx={{ borderRadius: 2, py: 1.4, fontSize: 15 }}
      >
        Find opportunities on {platform.name}
      </Button>
    )
  ) : pending ? (
    <Tooltip title="The connector for this platform has not been built yet.">
      <span style={{ display: "block" }}>
        <Button variant="outlined" disabled fullWidth sx={{ borderRadius: 2 }}>
          Not connected yet
        </Button>
      </span>
    </Tooltip>
  ) : null;

  return (
    <Surface
      accent={live ? "success" : "none"}
      interactive={!live}
      sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}
    >
      <Box
        sx={{
          px: { xs: 2.5, md: 3 },
          pt: 2.5,
          pb: 2.25,
          borderBottom: 1,
          borderColor: (t) => hairline(t),
        }}
      >
        {header}
      </Box>

      {wide && tuning ? (
        /* The live card. Narrative on the left, the controls you came for
           on the right, on a tinted panel so they read as one tool. */
        <Box
          sx={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "minmax(0, 5fr) minmax(0, 7fr)" },
            alignItems: "stretch",
          }}
        >
          <Box sx={{ p: { xs: 2.5, md: 3 } }}>{narrative}</Box>
          <Box
            sx={{
              p: { xs: 2.5, md: 3 },
              borderLeft: { xs: 0, md: 1 },
              borderTop: { xs: 1, md: 0 },
              borderColor: (t) => hairline(t),
              bgcolor: (t) => alpha(t.palette.text.primary, t.palette.mode === "dark" ? 0.03 : 0.02),
            }}
          >
            {tuning}
          </Box>
        </Box>
      ) : wide ? (
        /* Full width with nothing to tune. Let the fields sit side by side
           rather than stacking down one column beside empty space. */
        <Box
          sx={{
            flex: 1,
            p: { xs: 2.5, md: 3 },
            display: "grid",
            gap: 3,
            alignItems: "start",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(240px, 1fr))" },
          }}
        >
          {blocks}
        </Box>
      ) : (
        <Stack sx={{ flex: 1, p: { xs: 2.5, md: 3 } }} gap={2.5}>
          {narrative}
          {tuning}
        </Stack>
      )}

      {action && (
        <Box
          sx={{
            p: { xs: 2.5, md: 3 },
            pt: 0,
            ...(wide && {
              pt: { xs: 2.5, md: 3 },
              borderTop: 1,
              borderColor: (t) => hairline(t),
            }),
          }}
        >
          {action}
        </Box>
      )}
    </Surface>
  );
}
