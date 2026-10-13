import { useState } from "react";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import TravelExploreIcon from "@mui/icons-material/TravelExplore";

interface Props {
  disabled: boolean;
  onSubmit: (name: string, url: string) => Promise<void>;
}

/**
 * Name and website. Nothing else.
 *
 * Validation is deliberately thin: the backend canonicalizes the URL and
 * knows far more about what is acceptable than a regular expression here
 * ever could, and it returns a message written for a person.
 */
export default function ProductForm({ disabled, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSubmit(name.trim(), url.trim());
      setName("");
      setUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper variant="outlined" component="form" onSubmit={submit} sx={{ p: { xs: 2.5, md: 3 } }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Read a product website
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "58ch" }}>
        We look for a documentation section first. If the site has one we read only
        that, because it is where the real explanation lives. If it has none, we read
        the pages most likely to say what the product does, and skip the blog and the
        job adverts.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
        <TextField
          label="Product name"
          placeholder="Acme"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={disabled || busy}
        />
        <TextField
          label="Website"
          placeholder="example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          disabled={disabled || busy}
          helperText="https:// is optional"
        />
        <Button
          type="submit"
          variant="contained"
          size="large"
          startIcon={<TravelExploreIcon />}
          disabled={disabled || busy || !name.trim() || !url.trim()}
          sx={{ flexShrink: 0, mt: { sm: 0.25 } }}
        >
          {busy ? "Starting…" : "Read it"}
        </Button>
      </Stack>
    </Paper>
  );
}
