import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { PageHeader } from "@/components/StateBlocks";
import { productApi } from "@/lib/productApi";

const DESCRIPTION_MIN = 25;

/**
 * The product profile.
 *
 * Four fields. Submitting registers the product and starts reading its
 * website, which is where the rest of the system gets its understanding of
 * what this thing actually is.
 */
export default function NewProductRoute() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [goal, setGoal] = useState("");

  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shortDescription =
    touched && description.trim().length > 0 && description.trim().length < DESCRIPTION_MIN;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);

    if (!name.trim() || !url.trim() || description.trim().length < DESCRIPTION_MIN) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const product = await productApi.create({
        name: name.trim(),
        url: url.trim(),
        description: description.trim(),
        goal: goal.trim(),
      });
      navigate(`/products/${product.id}/reading`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the product.");
      setBusy(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 680, mx: "auto", px: 2, py: { xs: 4, md: 7 } }}>
      <PageHeader eyebrow="New product" title="Tell us about your product">
        Four things. We read your website afterwards to fill in the rest, so keep
        these short and in your own words.
      </PageHeader>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Paper
        variant="outlined"
        component="form"
        onSubmit={submit}
        noValidate
        sx={{ p: { xs: 2.5, md: 4 } }}
      >
        <Stack spacing={3}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              autoFocus
              label="Product name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={touched && !name.trim()}
              helperText={touched && !name.trim() ? "Required." : " "}
            />
            <TextField
              label="Website"
              placeholder="yourproduct.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              error={touched && !url.trim()}
              helperText={
                touched && !url.trim() ? "Required." : "https:// is optional."
              }
            />
          </Stack>

          <Divider />

          <TextField
            label="What does it do?"
            placeholder="A scheduling tool for dental clinics that fills last-minute cancellations automatically."
            multiline
            minRows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => setTouched(true)}
            error={shortDescription || (touched && !description.trim())}
            helperText={
              shortDescription || (touched && !description.trim())
                ? "Write at least one full sentence. This is what finds people describing the same problem in completely different words."
                : "Plain English. Describe the problem it solves, not the features."
            }
          />

          <TextField
            label="What are you trying to achieve?"
            placeholder="Our first 100 paying customers"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            helperText="Optional, but it changes a lot. Finding early customers and finding hires look nothing alike."
          />

          <Divider />

          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ sm: "center" }}
          >
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {busy ? "Saving…" : "Continue"}
            </Button>
            <Typography variant="caption" color="text.secondary">
              Next we read your website. It takes from ten seconds to a few minutes.
            </Typography>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
}
