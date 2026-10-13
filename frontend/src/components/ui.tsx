/* ------------------------------------------------------------------ *
 * The visual vocabulary the plan screen is built from.
 *
 * Before this existed every section reached for `Paper variant="outlined"`
 * and nothing else, so a hero, a control panel and a footnote all carried
 * the same weight — the page read as a stack of identical grey boxes with
 * no way to tell what mattered. Depth is the cheapest hierarchy there is,
 * and it was the one thing not being used.
 *
 * Everything here derives from the palette rather than naming colours, so
 * both schemes stay correct and a theme change reaches the whole screen.
 * ------------------------------------------------------------------ */

import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha, type SxProps, type Theme } from "@mui/material/styles";

/** Layered rather than one blur: a tight contact shadow plus a soft cast. */
export const shadow = (t: Theme, lifted = false) => {
  const ink = t.palette.mode === "dark" ? "#000" : "#0E151B";
  return lifted
    ? `0 1px 2px ${alpha(ink, 0.06)}, 0 12px 32px -8px ${alpha(ink, t.palette.mode === "dark" ? 0.6 : 0.14)}`
    : `0 1px 2px ${alpha(ink, 0.05)}, 0 4px 12px -6px ${alpha(ink, t.palette.mode === "dark" ? 0.5 : 0.09)}`;
};

/** A hairline that reads as an edge in light and as a seam in dark. */
export const hairline = (t: Theme) =>
  t.palette.mode === "dark" ? alpha("#FFF", 0.09) : alpha("#0E151B", 0.09);

interface SurfaceProps {
  children: ReactNode;
  /** Raises the card and lets it lift on hover. For things you act on. */
  interactive?: boolean;
  /** Tints the whole surface with the accent. For the one that matters most. */
  accent?: "primary" | "success" | "none";
  padding?: number | { xs: number; md: number };
  /* A real sx type, not `object`. As `object` every theme callback a
     caller writes loses its parameter type and trips noImplicitAny. */
  sx?: SxProps<Theme>;
}

/**
 * The one card in the app.
 *
 * `accent` is deliberately hard to reach for: the moment two cards on a
 * screen are both tinted, neither is emphasised any more.
 */
export function Surface({
  children,
  interactive = false,
  accent = "none",
  padding,
  sx = {},
}: SurfaceProps) {
  return (
    <Paper
      elevation={0}
      sx={{
        position: "relative",
        borderRadius: 3,
        border: 1,
        borderColor: (t) =>
          accent === "none" ? hairline(t) : alpha(t.palette[accent].main, 0.28),
        bgcolor: "background.paper",
        backgroundImage: (t) =>
          accent === "none"
            ? "none"
            : `linear-gradient(180deg, ${alpha(t.palette[accent].main, t.palette.mode === "dark" ? 0.07 : 0.04)} 0%, transparent 220px)`,
        boxShadow: (t) => shadow(t, interactive),
        transition: "box-shadow .22s ease, transform .22s ease, border-color .22s ease",
        ...(interactive && {
          "&:hover": {
            boxShadow: (t: Theme) => shadow(t, true),
            transform: "translateY(-2px)",
          },
        }),
        ...(padding !== undefined && { p: padding }),
        ...(sx as object),
      }}
    >
      {children}
    </Paper>
  );
}

/**
 * A section title with an accent rule beside it.
 *
 * The rule is doing real work: without a left edge to hang from, a heading
 * floating above a grid reads as a caption for the whole page rather than
 * a label for the block underneath it.
 */
export function SectionHead({
  title,
  hint,
  count,
  tone = "default",
  action,
}: {
  title: string;
  hint?: string;
  count?: number;
  tone?: "default" | "live";
  action?: ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      justifyContent="space-between"
      alignItems={{ xs: "flex-start", sm: "flex-end" }}
      gap={1.5}
      sx={{ mb: 2.5 }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Stack direction="row" alignItems="center" gap={1.5}>
          <Box
            sx={{
              width: 3,
              height: 20,
              borderRadius: 4,
              flexShrink: 0,
              bgcolor: tone === "live" ? "success.main" : "primary.main",
            }}
          />
          <Typography
            sx={{ fontWeight: 700, fontSize: { xs: 19, md: 21 }, letterSpacing: "-.02em" }}
          >
            {title}
          </Typography>
          {count !== undefined && (
            <Chip
              size="small"
              label={count}
              sx={{
                height: 21,
                minWidth: 25,
                fontSize: 11.5,
                fontWeight: 700,
                border: 1,
                borderColor: (t) =>
                  alpha(t.palette[tone === "live" ? "success" : "primary"].main, 0.32),
                color: tone === "live" ? "success.main" : "primary.main",
                bgcolor: (t) =>
                  alpha(t.palette[tone === "live" ? "success" : "primary"].main, 0.09),
              }}
            />
          )}
        </Stack>
        {hint && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.75, ml: 3, maxWidth: "76ch" }}
          >
            {hint}
          </Typography>
        )}
      </Box>
      {action && <Box sx={{ flexShrink: 0 }}>{action}</Box>}
    </Stack>
  );
}

/** The small caps label above a value. Used everywhere, so it lives here. */
export function Label({ children }: { children: ReactNode }) {
  return (
    <Typography
      component="div"
      sx={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: ".13em",
        textTransform: "uppercase",
        color: "text.secondary",
        lineHeight: 1.7,
      }}
    >
      {children}
    </Typography>
  );
}

/** An icon in a tinted, rounded tile. The app's one icon treatment. */
export function IconTile({
  children,
  tone = "muted",
  size = 38,
}: {
  children: ReactNode;
  tone?: "muted" | "primary" | "success";
  size?: number;
}) {
  return (
    <Box
      sx={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: 2,
        display: "grid",
        placeItems: "center",
        border: 1,
        borderColor: (t) =>
          tone === "muted" ? hairline(t) : alpha(t.palette[tone].main, 0.3),
        bgcolor: (t) =>
          tone === "muted"
            ? alpha(t.palette.text.primary, t.palette.mode === "dark" ? 0.06 : 0.04)
            : alpha(t.palette[tone].main, t.palette.mode === "dark" ? 0.16 : 0.1),
        color: tone === "muted" ? "text.secondary" : `${tone}.main`,
        "& svg": { fontSize: size * 0.5 },
      }}
    >
      {children}
    </Box>
  );
}
