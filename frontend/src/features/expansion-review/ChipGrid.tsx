import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import AddIcon from "@mui/icons-material/Add";

import { MONO } from "@/styles/theme";
import type { PlanTerm } from "@/lib/types";

interface Props {
  terms: PlanTerm[];
  onChange: (next: PlanTerm[]) => void;
}

/**
 * The terms the plan will actually execute.
 *
 * Every expansion term carries a reason. If we add words silently and the
 * expansion is wrong, the user gets bad results and blames the product.
 */
export default function ChipGrid({ terms, onChange }: Props) {
  const [typed, setTyped] = useState("");

  const remove = (term: string) => onChange(terms.filter((t) => t.term !== term));

  const add = () => {
    const term = typed.trim();
    if (!term) return;
    if (!terms.some((t) => t.term.toLowerCase() === term.toLowerCase())) {
      onChange([...terms, { term, origin: "user" }]);
    }
    setTyped("");
  };

  const expansions = terms.filter((t) => t.origin === "expansion");

  return (
    <Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 2.5 }}>
        {terms.map((t) => {
          const chip = (
            <Chip
              label={t.term}
              onDelete={() => remove(t.term)}
              size="small"
              color={t.origin === "user" ? "primary" : "default"}
              variant={t.origin === "user" ? "filled" : "outlined"}
            />
          );
          return t.reason ? (
            <Tooltip key={t.term} title={t.reason} arrow>
              <span>{chip}</span>
            </Tooltip>
          ) : (
            <Box key={t.term} component="span">
              {chip}
            </Box>
          );
        })}
      </Box>

      <Stack direction="row" spacing={1} sx={{ mb: 2.5 }}>
        <TextField
          size="small"
          label="Add a term"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button startIcon={<AddIcon />} onClick={add} variant="outlined">
          Add
        </Button>
      </Stack>

      {expansions.length > 0 && (
        <>
          <Divider sx={{ mb: 2 }} />
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
            Why the compiler added each one
          </Typography>
          <Stack spacing={1}>
            {expansions.map((t) => (
              <Stack key={t.term} direction="row" spacing={2} alignItems="baseline">
                <Typography sx={{ fontFamily: MONO, fontSize: 12.5, minWidth: 168 }}>
                  {t.term}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                  {t.reason}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}
