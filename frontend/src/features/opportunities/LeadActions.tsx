/* ------------------------------------------------------------------ *
 * Marking a lead off.
 *
 * The whole reason the lead table exists. Without this the results screen
 * is a list you re-read every week, with no way to record that you already
 * replied to the third one.
 *
 * The state is written optimistically and rolled back if the server
 * disagrees. Waiting for a round trip before the button moves makes
 * working through twenty leads feel like twenty separate transactions,
 * which is exactly the friction that stops anybody doing it.
 * ------------------------------------------------------------------ */

import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import ReplyIcon from "@mui/icons-material/ReplyOutlined";
import StarIcon from "@mui/icons-material/StarBorder";
import UndoIcon from "@mui/icons-material/Undo";

import { productApi, type Lead, type LeadState } from "@/lib/productApi";

/** Which colour each state answers to. `new` has none: it is the absence. */
const TONE: Record<Exclude<LeadState, "new">, "primary" | "success" | "warning"> = {
  replied: "primary",
  won: "success",
  ignored: "warning",
};

const DONE_LABEL: Record<Exclude<LeadState, "new">, string> = {
  replied: "Replied",
  won: "Won",
  ignored: "Ignored",
};

interface Props {
  lead: Lead | undefined;
  /** Report the new state upward so counts and filters stay honest. */
  onChanged: (lead: Lead) => void;
}

export default function LeadActions({ lead, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  // No lead row yet. Happens on results from a run that finished before
  // this feature existed, and there is nothing useful to offer for them.
  if (!lead) return null;

  const move = async (state: LeadState) => {
    setBusy(true);
    setFailed(false);

    // Optimistic. The row moves now; the server is asked afterwards.
    const before = lead;
    onChanged({ ...lead, state });

    try {
      onChanged(await productApi.updateLead(lead.id, state));
    } catch {
      onChanged(before);
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  if (lead.state !== "new") {
    const tone = TONE[lead.state];
    return (
      <Stack direction="row" alignItems="center" gap={1}>
        <Stack
          direction="row"
          alignItems="center"
          gap={0.75}
          sx={{
            px: 1.25,
            py: 0.5,
            borderRadius: 2,
            border: 1,
            borderColor: (t) => alpha(t.palette[tone].main, 0.35),
            bgcolor: (t) => alpha(t.palette[tone].main, 0.1),
            color: `${tone}.main`,
          }}
        >
          <CheckIcon sx={{ fontSize: 14 }} />
          <Typography sx={{ fontSize: 12, fontWeight: 650 }}>
            {DONE_LABEL[lead.state]}
          </Typography>
        </Stack>

        <Tooltip title="Put it back on the list">
          <Box component="span">
            <Button
              size="small"
              disabled={busy}
              onClick={() => move("new")}
              sx={{ minWidth: 0, px: 1, borderRadius: 2, color: "text.secondary" }}
            >
              <UndoIcon sx={{ fontSize: 15 }} />
            </Button>
          </Box>
        </Tooltip>
      </Stack>
    );
  }

  return (
    <Stack direction="row" alignItems="center" gap={0.75} flexWrap="wrap">
      <Action
        icon={<ReplyIcon sx={{ fontSize: 15 }} />}
        label="Replied"
        tone="primary"
        busy={busy}
        onClick={() => move("replied")}
      />
      <Action
        icon={<StarIcon sx={{ fontSize: 15 }} />}
        label="Won"
        tone="success"
        busy={busy}
        onClick={() => move("won")}
      />
      <Action
        icon={<CloseIcon sx={{ fontSize: 15 }} />}
        label="Ignore"
        tone="muted"
        busy={busy}
        onClick={() => move("ignored")}
      />
      {failed && (
        <Typography variant="caption" color="error.main">
          Could not save
        </Typography>
      )}
    </Stack>
  );
}

function Action({
  icon,
  label,
  tone,
  busy,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  tone: "primary" | "success" | "muted";
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      size="small"
      startIcon={icon}
      disabled={busy}
      onClick={onClick}
      sx={{
        px: 1.25,
        py: 0.4,
        minWidth: 0,
        borderRadius: 2,
        fontSize: 12,
        fontWeight: 600,
        color: tone === "muted" ? "text.secondary" : `${tone}.main`,
        "& .MuiButton-startIcon": { mr: 0.5 },
        "&:hover": {
          bgcolor: (t) =>
            alpha(
              tone === "muted" ? t.palette.text.primary : t.palette[tone].main,
              0.08,
            ),
        },
      }}
    >
      {label}
    </Button>
  );
}
