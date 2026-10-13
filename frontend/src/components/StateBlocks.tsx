import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";

import { Surface } from "./ui";

/* Loading, empty and failed. A blank page is never acceptable. */

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <Stack alignItems="center" spacing={2.25} sx={{ py: { xs: 7, md: 10 } }}>
      <CircularProgress size={24} thickness={4.5} />
      <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 560 }}>
        {label}
      </Typography>
    </Stack>
  );
}

export function ErrorBlock({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Surface
      padding={{ xs: 2.5, md: 3 }}
      sx={{
        borderColor: (t) => alpha(t.palette.error.main, 0.35),
        backgroundImage: (t) =>
          `linear-gradient(180deg, ${alpha(t.palette.error.main, t.palette.mode === "dark" ? 0.09 : 0.05)} 0%, transparent 160px)`,
      }}
    >
      <Stack direction="row" gap={2}>
        <Box
          sx={{
            width: 38,
            height: 38,
            flexShrink: 0,
            borderRadius: 2,
            display: "grid",
            placeItems: "center",
            border: 1,
            borderColor: (t) => alpha(t.palette.error.main, 0.3),
            bgcolor: (t) => alpha(t.palette.error.main, 0.11),
            color: "error.main",
          }}
        >
          <ErrorOutlineIcon sx={{ fontSize: 19 }} />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontWeight: 680, fontSize: 16, letterSpacing: "-.012em" }}>
            That did not work
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.5, mb: onRetry ? 2.25 : 0, lineHeight: 1.7 }}
          >
            {message} Nothing was spent.
          </Typography>
          {onRetry && (
            <Button variant="outlined" size="small" onClick={onRetry} color="error">
              Try again
            </Button>
          )}
        </Box>
      </Stack>
    </Surface>
  );
}

export function PageHeader({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={2}
      alignItems={{ sm: "flex-end" }}
      sx={{ mb: 3 }}
    >
      <Box sx={{ flex: 1 }}>
        <Typography
          sx={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: ".18em",
            textTransform: "uppercase",
            color: "primary.main",
            mb: 0.75,
          }}
        >
          {eyebrow}
        </Typography>
        <Typography
          component="h1"
          sx={{ fontSize: { xs: 26, md: 32 }, fontWeight: 720, letterSpacing: "-.03em", lineHeight: 1.15 }}
        >
          {title}
        </Typography>
        {children && (
          <Typography
            variant="body2"
            sx={{ color: "text.secondary", maxWidth: "62ch", mt: 1.25, lineHeight: 1.7 }}
          >
            {children}
          </Typography>
        )}
      </Box>
      {action}
    </Stack>
  );
}
