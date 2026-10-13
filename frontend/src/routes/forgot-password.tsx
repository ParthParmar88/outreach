import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import AuthCard from "@/features/auth/AuthCard";
import { authApi, type ForgotPasswordResult } from "@/lib/authApi";
import { MONO } from "@/styles/theme";

/**
 * Ask for a reset link.
 *
 * The screen never says whether the address has an account, because the
 * server never says either. Confirming that would hand anyone with a list
 * of addresses a free way to find out which of them are customers.
 */
export default function ForgotPasswordRoute() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForgotPasswordResult | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;

    setBusy(true);
    setError(null);
    try {
      setResult(await authApi.forgotPassword(email.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the link.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Forgotten your password"
      subtitle="Give us the email you signed up with and we will send you a link to set a new one."
      footer={
        <>
          Remembered it?{" "}
          <Link component={RouterLink} to="/login">
            Sign in
          </Link>
        </>
      }
    >
      {result ? (
        <Stack spacing={2}>
          <Alert severity={result.link ? "warning" : "success"}>
            {result.message}
          </Alert>

          {/* Only ever present on a local machine with no mail server. It is
              the difference between a reset flow you can finish in
              development and one that dead-ends at a log line. */}
          {result.link && (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                No email was sent, because this machine has no mail server set
                up. Open this link to carry on:
              </Typography>
              <Box
                sx={{
                  p: 1.5,
                  borderRadius: 1,
                  border: 1,
                  borderColor: "divider",
                  bgcolor: "action.hover",
                  fontFamily: MONO,
                  fontSize: 12,
                  wordBreak: "break-all",
                  mb: 1.5,
                }}
              >
                {result.link}
              </Box>
              <Button
                variant="contained"
                fullWidth
                href={result.link}
                sx={{ py: 1.2 }}
              >
                Open the reset link
              </Button>
            </Box>
          )}

          {result.sent && (
            <Typography variant="body2" color="text.secondary">
              The link works once, and stops working after an hour. If nothing
              arrives, check the spam folder before asking for another.
            </Typography>
          )}

          <Button onClick={() => setResult(null)} sx={{ alignSelf: "flex-start" }}>
            Use a different email
          </Button>
        </Stack>
      ) : (
        <Stack component="form" onSubmit={submit} noValidate spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}

          <TextField
            autoFocus
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />

          <Button
            type="submit"
            variant="contained"
            size="large"
            disabled={busy}
            sx={{ py: 1.3 }}
          >
            {busy ? "Sending…" : "Send the reset link"}
          </Button>
        </Stack>
      )}
    </AuthCard>
  );
}
