import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";

import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import { MONO } from "@/styles/theme";

interface Props {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

/**
 * The frame both auth screens sit in.
 *
 * Shared so that sign up and sign in cannot drift apart. Two pages that do
 * almost the same thing looking almost the same is worse than looking
 * identical.
 */
export default function AuthCard({ title, subtitle, children, footer }: Props) {
  const theme = useTheme();
  const dark = theme.palette.mode === "dark";

  return (
    <Box
      sx={{
        minHeight: "100dvh",
        bgcolor: "background.default",
        display: "grid",
        placeItems: "center",
        px: 2,
        py: 6,
      }}
    >
      <Stack spacing={3} sx={{ width: "100%", maxWidth: 420 }}>
        <Stack spacing={1} sx={{ textAlign: "center", alignItems: "center" }}>
          <Typography
            component={RouterLink}
            to="/"
            sx={{
              fontFamily: MONO,
              fontSize: 11,
              letterSpacing: ".18em",
              textTransform: "uppercase",
              color: "text.secondary",
              textDecoration: "none",
            }}
          >
            Outreach
          </Typography>
          <Typography
            component="h1"
            sx={{ fontSize: 26, fontWeight: 660, letterSpacing: "-0.025em" }}
          >
            {title}
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", maxWidth: "38ch" }}>
            {subtitle}
          </Typography>
        </Stack>

        <Paper
          variant="outlined"
          sx={{
            p: { xs: 2.5, sm: 3 },
            borderRadius: 3,
            boxShadow: `0 30px 70px -50px ${alpha(theme.palette.common.black, dark ? 1 : 0.6)}`,
          }}
        >
          {children}
        </Paper>

        <Typography variant="body2" sx={{ textAlign: "center", color: "text.secondary" }}>
          {footer}
        </Typography>
      </Stack>
    </Box>
  );
}
