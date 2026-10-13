import { useState } from "react";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import AddIcon from "@mui/icons-material/Add";

import { MONO } from "@/styles/theme";

interface Props {
  label: string;
  hint?: string;
  values: string[];
  placeholder: string;
  onChange: (next: string[]) => void;
  /** Flags values that will search badly, so the reason is visible up front. */
  warn?: (value: string) => string | null;
}

/**
 * A list the user can correct before spending a run.
 *
 * The planner has never seen a result. It is a good first guess and a poor
 * last word, and making somebody rewrite an entire plan to change one search
 * term is the kind of friction that stops people tuning anything at all.
 */
export default function EditableChips({
  label,
  hint,
  values,
  placeholder,
  onChange,
  warn,
}: Props) {
  const [typed, setTyped] = useState("");

  const add = () => {
    const value = typed.trim();
    if (!value) return;
    if (!values.some((v) => v.toLowerCase() === value.toLowerCase())) {
      onChange([...values, value]);
    }
    setTyped("");
  };

  const remove = (value: string) => onChange(values.filter((v) => v !== value));

  return (
    <Box>
      <Stack direction="row" alignItems="baseline" gap={1} sx={{ mb: 0.25 }}>
        <Typography
          variant="overline"
          sx={{
            fontSize: 10,
            letterSpacing: ".1em",
            color: "text.secondary",
            lineHeight: 1.8,
          }}
        >
          {label}
        </Typography>
        <Typography
          variant="caption"
          sx={{ fontFamily: MONO, fontSize: 11, color: "text.disabled" }}
        >
          {values.length}
        </Typography>
      </Stack>

      {hint && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", maxWidth: "58ch" }}
        >
          {hint}
        </Typography>
      )}

      <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1.25, mb: 1.25 }}>
        {values.map((value) => {
          const problem = warn?.(value) ?? null;
          return (
            <Chip
              key={value}
              size="small"
              label={value}
              onDelete={() => remove(value)}
              color={problem ? "warning" : "default"}
              variant={problem ? "filled" : "outlined"}
              title={problem ?? undefined}
              sx={{
                fontFamily: MONO,
                fontSize: 11.5,
                height: 26,
                bgcolor: problem ? undefined : "background.paper",
              }}
            />
          );
        })}
        {values.length === 0 && (
          <Typography variant="caption" color="text.disabled">
            none yet — add one below
          </Typography>
        )}
      </Stack>

      <TextField
        size="small"
        fullWidth
        value={typed}
        placeholder={placeholder}
        onChange={(e) => setTyped(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        slotProps={{
          input: {
            // Explicit, because this often sits on a tinted panel where an
            // inherited transparent field would disappear into the backing.
            sx: { fontFamily: MONO, fontSize: 12.5, bgcolor: "background.paper" },
            endAdornment: (
              <InputAdornment position="end">
                <IconButton size="small" onClick={add} disabled={!typed.trim()}>
                  <AddIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ),
          },
        }}
      />
    </Box>
  );
}
