import { Link as RouterLink } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";

import ConversationField from "@/features/landing/ConversationField";
import { useAuth } from "@/lib/auth";
import { MONO } from "@/styles/theme";

interface Props {
  mode: "light" | "dark";
  onToggleMode: () => void;
}

/**
 * The way in. One promise and one button.
 *
 * Whatever we need to know is asked after somebody has decided to be here,
 * not before.
 */
export default function LandingRoute({ mode, onToggleMode }: Props) {
  const theme = useTheme();
  const dark = theme.palette.mode === "dark";
  const { user } = useAuth();

  return (
    <Box
      sx={{
        position: "relative",
        minHeight: "100dvh",
        overflow: "hidden",
        bgcolor: "background.default",
        display: "grid",
        placeItems: "center",
        px: 2,
        py: 6,
      }}
    >
      <ConversationField />

      {/* Pulls the eye to the middle and keeps the quotes from competing
          with the words that matter. */}
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background: `radial-gradient(ellipse 62% 55% at 50% 48%, ${alpha(
            theme.palette.background.default,
            dark ? 0.97 : 0.94,
          )} 34%, ${alpha(theme.palette.background.default, 0)} 78%)`,
        }}
      />

      <Tooltip title={mode === "light" ? "Dark theme" : "Light theme"}>
        <IconButton
          size="small"
          onClick={onToggleMode}
          sx={{ position: "absolute", top: 16, right: 16, zIndex: 3 }}
        >
          {mode === "light" ? (
            <DarkModeOutlinedIcon fontSize="small" />
          ) : (
            <LightModeOutlinedIcon fontSize="small" />
          )}
        </IconButton>
      </Tooltip>

      <Stack
        spacing={4}
        sx={{
          position: "relative",
          zIndex: 2,
          width: "100%",
          maxWidth: 620,
          alignItems: "center",
          textAlign: "center",
        }}
      >
        <Typography
          sx={{
            fontFamily: MONO,
            fontSize: 11,
            letterSpacing: ".18em",
            textTransform: "uppercase",
            color: "text.secondary",
          }}
        >
          Outreach
        </Typography>

        <Typography
          component="h1"
          sx={{
            fontSize: "clamp(30px, 5.4vw, 46px)",
            lineHeight: 1.08,
            letterSpacing: "-0.03em",
            fontWeight: 660,
            textWrap: "balance",
          }}
        >
          They already wrote
          <br />
          your problem down.
        </Typography>

        <Typography
          sx={{
            fontSize: "clamp(15px, 1.7vw, 17px)",
            lineHeight: 1.6,
            color: "text.secondary",
            maxWidth: "48ch",
          }}
        >
          Every day, somebody describes the problem your product solves. In public,
          in their own words, using none of your keywords. Whatever you sell, this
          finds them, ranks them, and shows you the sentence that proves it.
        </Typography>

        <Stack spacing={1.5} alignItems="center">
          <Button
            component={RouterLink}
            to={user ? "/home" : "/signup"}
            variant="contained"
            size="large"
            endIcon={<ArrowForwardIcon />}
            sx={{ py: 1.4, px: 4, fontSize: 15 }}
          >
            {user ? "Back to your products" : "Start free demo"}
          </Button>

          {!user && (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Already have an account?{" "}
              <Link component={RouterLink} to="/login">
                Sign in
              </Link>
            </Typography>
          )}
        </Stack>

        <Typography sx={{ fontSize: 12.5, color: "text.secondary" }}>
          No card required. We read public posts only, and never post anything on
          your behalf.
        </Typography>
      </Stack>
    </Box>
  );
}
