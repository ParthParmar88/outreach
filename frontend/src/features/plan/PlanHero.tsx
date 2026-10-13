/* ------------------------------------------------------------------ *
 * The top of the plan screen.
 *
 * What was here before was a label, a name and four grey words on a plain
 * background — correct, and it opened the page on nothing. A product
 * screen has to establish what you are looking at before it starts
 * explaining itself, and the facts to do that with (pages read, channels,
 * when it was written) were already on the page as unpunctuated prose.
 *
 * So: the same facts, given shape. The tint is keyed to the primary colour
 * and fades out within the header's own height, which anchors the page
 * without turning into decoration that competes with the content below.
 * ------------------------------------------------------------------ */

import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import LanguageIcon from "@mui/icons-material/LanguageOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";

import { hairline } from "@/components/ui";

interface Props {
  name: string;
  domain?: string;
  stats: { value: ReactNode; label: string }[];
  onRewrite?: () => void;
  rewriting?: boolean;
}

export default function PlanHero({ name, domain, stats, onRewrite, rewriting }: Props) {
  return (
    <Box
      sx={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 3,
        border: 1,
        borderColor: (t) => hairline(t),
        bgcolor: "background.paper",
        // Two stops: a wash of brand across the top, and a highlight in the
        // corner so the block is not a flat rectangle of tint.
        backgroundImage: (t) => `
          radial-gradient(120% 140% at 88% -30%, ${alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.22 : 0.13)} 0%, transparent 62%),
          linear-gradient(180deg, ${alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.09 : 0.055)} 0%, transparent 78%)
        `,
        px: { xs: 2.5, md: 4 },
        py: { xs: 3, md: 4 },
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        gap={2.5}
      >
        <Box sx={{ minWidth: 0 }}>
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
            Marketing plan
          </Typography>

          <Typography
            component="h1"
            sx={{
              fontSize: { xs: 30, md: 40 },
              fontWeight: 720,
              letterSpacing: "-.03em",
              lineHeight: 1.1,
            }}
          >
            {name}
          </Typography>

          {domain && (
            <Stack direction="row" alignItems="center" gap={0.75} sx={{ mt: 1.25 }}>
              <LanguageIcon sx={{ fontSize: 15, color: "text.secondary" }} />
              <Typography variant="body2" color="text.secondary">
                {domain}
              </Typography>
            </Stack>
          )}
        </Box>

        {onRewrite && (
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={onRewrite}
            disabled={rewriting}
            sx={{
              flexShrink: 0,
              borderRadius: 2,
              bgcolor: "background.paper",
              borderColor: (t) => alpha(t.palette.primary.main, 0.35),
            }}
          >
            {rewriting ? "Rewriting…" : "Rewrite plan"}
          </Button>
        )}
      </Stack>

      {/* The facts, as figures rather than a sentence. A number you can
          read at a glance is the difference between a header that informs
          and one that is merely present. */}
      {stats.length > 0 && (
        <Stack
          direction="row"
          flexWrap="wrap"
          gap={{ xs: 2, md: 4 }}
          sx={{
            mt: { xs: 3, md: 3.5 },
            pt: { xs: 2.5, md: 3 },
            borderTop: 1,
            borderColor: (t) => hairline(t),
          }}
        >
          {stats.map((s) => (
            <Box key={s.label} sx={{ minWidth: 72 }}>
              <Typography
                sx={{ fontSize: { xs: 19, md: 22 }, fontWeight: 700, letterSpacing: "-.02em", lineHeight: 1.2 }}
              >
                {s.value}
              </Typography>
              <Typography
                sx={{
                  fontSize: 10.5,
                  fontWeight: 600,
                  letterSpacing: ".1em",
                  textTransform: "uppercase",
                  color: "text.secondary",
                  mt: 0.25,
                }}
              >
                {s.label}
              </Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}
