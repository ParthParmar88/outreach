import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";

import AuthCard from "@/features/auth/AuthCard";
import { useAuth } from "@/lib/auth";

const MIN_PASSWORD = 8;

export default function SignUpRoute() {
  const { user, loading, signUp } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && user) return <Navigate to="/home" replace />;

  const passwordShort = touched && password.length > 0 && password.length < MIN_PASSWORD;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!name.trim() || !email.trim() || password.length < MIN_PASSWORD) return;

    setBusy(true);
    setError(null);
    try {
      await signUp(name.trim(), email.trim(), password);
      // Straight into building the first product. Making somebody sign in
      // again immediately after signing up is a form for no reason.
      navigate("/new", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account.");
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Create your account"
      subtitle="Then tell us about your product, and we will go and find the people talking about the problem it solves."
      footer={
        <>
          Already have an account?{" "}
          <Link component={RouterLink} to="/login">
            Sign in
          </Link>
        </>
      }
    >
      <Stack component="form" onSubmit={submit} noValidate spacing={2}>
        {error && <Alert severity="error">{error}</Alert>}

        <TextField
          autoFocus
          label="Your name"
          placeholder="Nisarg"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={touched && !name.trim()}
          helperText={touched && !name.trim() ? "We need something to call you." : " "}
        />

        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={touched && !email.trim()}
          helperText={touched && !email.trim() ? "Required." : " "}
        />

        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched(true)}
          error={passwordShort}
          helperText={
            passwordShort
              ? `At least ${MIN_PASSWORD} characters.`
              : "At least 8 characters. Length matters more than symbols."
          }
        />

        <Button type="submit" variant="contained" size="large" disabled={busy} sx={{ py: 1.3 }}>
          {busy ? "Creating your account…" : "Create account"}
        </Button>
      </Stack>
    </AuthCard>
  );
}
