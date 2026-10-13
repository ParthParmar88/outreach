/* ------------------------------------------------------------------ *
 * What the product does and what the owner wants — editable in place.
 *
 * These two fields are the whole input to the planner: they decide the
 * search terms, the repositories, and what every result is judged against.
 * They were write-once until recently, set on the create form and never
 * reachable again, so getting them wrong meant making a second product and
 * re-crawling the same website. That is how an account ends up with three
 * rows of the same name, two of which nobody can tell apart.
 *
 * Saving does NOT rewrite the plan. Editing and re-planning are two
 * decisions: a typo correction should not silently spend a model call and
 * replace a plan somebody has hand-edited. Instead the plan goes stale on
 * its own — both fields are hashed into it — and this says so, with the
 * button that acts on it right there.
 * ------------------------------------------------------------------ */

import { useState, type ReactNode } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import EditIcon from "@mui/icons-material/EditOutlined";
import FlagIcon from "@mui/icons-material/OutlinedFlag";
import InventoryIcon from "@mui/icons-material/Inventory2Outlined";

import { IconTile, Label, Surface, hairline } from "@/components/ui";
import { productApi, type Product } from "@/lib/productApi";

/** Matches the server's own limits, so a save cannot fail on length. */
const MAX_DESCRIPTION = 4000;
const MAX_GOAL = 2000;

interface Props {
  product: Product;
  /** True when the plan no longer matches these fields. */
  stale: boolean;
  /** Re-read the product after a save. Whatever it returns is ignored. */
  onSaved: () => unknown | Promise<unknown>;
  /** Rewrite the plan. Offered here only once the text has moved on. */
  onRewrite: () => void;
}

export default function ProductBrief({ product, stale, onSaved, onRewrite }: Props) {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(product.description ?? "");
  const [goal, setGoal] = useState(product.goal ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = () => {
    // Re-seed from the product rather than trusting leftover state: the
    // page reloads it after every save and after every rewrite.
    setDescription(product.description ?? "");
    setGoal(product.goal ?? "");
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await productApi.update(product.id, {
        description: description.trim() || null,
        goal: goal.trim() || null,
      });
      await onSaved();
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const changed =
    description.trim() !== (product.description ?? "").trim() ||
    goal.trim() !== (product.goal ?? "").trim();

  return (
    <Surface sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Stack
        direction="row"
        alignItems="center"
        gap={1.5}
        sx={{
          px: { xs: 2.5, md: 3 },
          py: 2.25,
          borderBottom: 1,
          borderColor: (t) => hairline(t),
        }}
      >
        <IconTile tone="primary" size={34}>
          <EditIcon />
        </IconTile>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 680, fontSize: 16.5, letterSpacing: "-.01em" }}>
            Your brief
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Everything below is written from this
          </Typography>
        </Box>
        {!editing && (
          <Button size="small" onClick={open} sx={{ borderRadius: 2, flexShrink: 0 }}>
            Edit
          </Button>
        )}
      </Stack>

      <Box sx={{ px: { xs: 2.5, md: 3 }, py: 2.75, flex: 1 }}>
        {editing ? (
          <Stack gap={2.5}>
            <TextField
              label="What does it do?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              multiline
              minRows={4}
              fullWidth
              slotProps={{ htmlInput: { maxLength: MAX_DESCRIPTION } }}
              helperText="Describe the problem in the words someone with it would type. This is what finds people describing it differently."
            />
            <TextField
              label="What are you trying to achieve?"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              multiline
              minRows={3}
              fullWidth
              slotProps={{ htmlInput: { maxLength: MAX_GOAL } }}
              helperText="Finding early customers and finding hires produce completely different results."
            />

            {error && <Alert severity="error">{error}</Alert>}

            <Stack direction="row" gap={1}>
              <Button
                variant="contained"
                onClick={save}
                disabled={saving || !changed}
                sx={{ borderRadius: 2 }}
              >
                {saving ? "Saving…" : "Save changes"}
              </Button>
              <Button onClick={() => setEditing(false)} disabled={saving} sx={{ borderRadius: 2 }}>
                Cancel
              </Button>
            </Stack>
          </Stack>
        ) : (
          <Stack gap={2.75}>
            <Field
              icon={<InventoryIcon />}
              label="What it does"
              value={product.description}
              empty="Not set — the planner is working from the website alone."
            />
            <Field
              icon={<FlagIcon />}
              label="Your goal"
              value={product.goal}
              accent
              empty="Not set — results are not aimed at anything in particular."
            />
          </Stack>
        )}
      </Box>

      {/* Only after an edit has actually landed. Saying "out of date" next
          to text nobody has touched reads as a fault rather than a choice. */}
      {stale && !editing && (
        <Box sx={{ px: { xs: 2.5, md: 3 }, pb: 2.75 }}>
          <Alert
            severity="info"
            icon={<AutoFixHighIcon fontSize="inherit" />}
            sx={{ borderRadius: 2, alignItems: "center" }}
            action={
              <Button size="small" onClick={onRewrite} sx={{ borderRadius: 2 }}>
                Rewrite
              </Button>
            }
          >
            The plan was written from an earlier version of this.
          </Alert>
        </Box>
      )}
    </Surface>
  );
}

/**
 * One field of the brief.
 *
 * The rule down the left is what makes two paragraphs read as two fields
 * rather than as one block of text with a heading lost inside it.
 */
function Field({
  icon,
  label,
  value,
  empty,
  accent = false,
}: {
  icon: ReactNode;
  label: string;
  value: string | null;
  empty: string;
  accent?: boolean;
}) {
  return (
    <Box
      sx={{
        pl: 2,
        borderLeft: 2,
        borderColor: (t) => (accent ? alpha(t.palette.primary.main, 0.5) : hairline(t)),
      }}
    >
      <Stack direction="row" alignItems="center" gap={0.75} sx={{ mb: 0.75 }}>
        <Box
          sx={{
            display: "flex",
            color: accent ? "primary.main" : "text.secondary",
            "& svg": { fontSize: 14 },
          }}
        >
          {icon}
        </Box>
        <Label>{label}</Label>
      </Stack>
      <Typography
        variant="body2"
        sx={{
          lineHeight: 1.7,
          color: value ? "text.primary" : "text.disabled",
          fontStyle: value ? "normal" : "italic",
        }}
      >
        {value || empty}
      </Typography>
    </Box>
  );
}
