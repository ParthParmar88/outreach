import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";

import AuthCard from "@/features/auth/AuthCard";
import { useAuth } from "@/lib/auth";
import { authApi } from "@/lib/authApi";

/** Matches MIN_PASSWORD on the backend. Checked here only to save a round trip. */
const MIN_PASSWORD = 8;

/**
 * Set a new password from a reset link.
 *
 * Signing in on success is deliberate. Somebody who has proved they control
 * the mailbox and chosen a new password has already done the work twice,
 * and a login form here is exactly where people give up.
 */
export default function ResetPasswordRoute() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { user, loading, refresh } = useAuth();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && user) return <Navigate to="/home" replace />;

  // A link with nothing on it. Says so, rather than showing a form that
  // could only ever fail on submit.
  if (!token) {
    return (
      <AuthCard
        title="That link is incomplete"
        subtitle="The address is missing its reset code, which usually means the email client cut it in half."
        footer={
          <Link component={RouterLink} to="/forgot-password">
            Ask for a new link
          </Link>
        }
      >
        <Alert severity="warning">
          Copy the whole link out of the email, including everything after
          <b> ?token=</b>.
        </Alert>
      </AuthCard>
    );
  }

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && password !== confirm;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD || password !== confirm) return;

    setBusy(true);
    setError(null);
    try {
      await authApi.resetPassword(token, password);
      // The server signed us in with the same response. Tell the app so it
      // does not bounce straight back to the login page.
      await refresh();
      navigate("/home", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set the password.");
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="Once this is set you will be signed in straight away."
      footer={
        <>
          Link stopped working?{" "}
          <Link component={RouterLink} to="/forgot-password">
            Ask for a new one
          </Link>
        </>
      }
    >
      <Stack component="form" onSubmit={submit} noValidate spacing={2}>
        {error && <Alert severity="error">{error}</Alert>}

        <TextField
          autoFocus
          label="New password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={tooShort}
          helperText={
            tooShort
              ? `At least ${MIN_PASSWORD} characters.`
              : "Length matters more than punctuation. A short phrase beats P@ss1!"
          }
        />

        <TextField
          label="Type it again"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={mismatch}
          helperText={mismatch ? "These two do not match." : " "}
        />

        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={busy || password.length < MIN_PASSWORD || password !== confirm}
          sx={{ py: 1.3 }}
        >
          {busy ? "Setting…" : "Set the password and sign in"}
        </Button>
      </Stack>
    </AuthCard>
  );
}
