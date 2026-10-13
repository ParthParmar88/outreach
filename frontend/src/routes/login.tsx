import { useState } from "react";
import { Link as RouterLink, Navigate, useLocation, useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";

import AuthCard from "@/features/auth/AuthCard";
import { useAuth } from "@/lib/auth";

interface NavState {
  from?: string;
  reason?: "signed-out";
}

export default function LoginRoute() {
  const { user, loading, logIn } = useAuth();
  const navigate = useNavigate();
  const state = useLocation().state as NavState | null;
  const from = state?.from;
  const redirected = state?.reason === "signed-out";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && user) return <Navigate to="/home" replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password) return;

    setBusy(true);
    setError(null);
    try {
      await logIn(email.trim(), password);
      // Back to wherever they were headed before being asked to sign in.
      navigate(from ?? "/home", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to pick up one of your products."
      footer={
        <>
          No account yet?{" "}
          <Link component={RouterLink} to="/signup">
            Create one
          </Link>
        </>
      }
    >
      <Stack component="form" onSubmit={submit} noValidate spacing={2}>
        {redirected && !error && (
          <Alert severity="info">
            Please sign in to continue.
            {from ? ` We will take you back to ${from} afterwards.` : ""}
          </Alert>
        )}

        {error && <Alert severity="error">{error}</Alert>}

        <TextField
          autoFocus
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {/* Under the password field and above the button, which is where
            somebody looks the moment the password they typed is refused. */}
        <Link
          component={RouterLink}
          to="/forgot-password"
          variant="body2"
          sx={{ alignSelf: "flex-end", mt: -1 }}
        >
          Forgotten your password?
        </Link>

        <Button type="submit" variant="contained" size="large" disabled={busy} sx={{ py: 1.3 }}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </Stack>
    </AuthCard>
  );
}
