import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import { MONO } from "@/styles/theme";

/* ================================================================== *
 * The background is the product.
 *
 * Real posts drift past: mostly noise, two of them pulled into focus with
 * a score. That is the entire thesis as a picture, before a word of
 * explanation. A gradient would have said nothing.
 *
 * Every quote below is real, from the August GitHub and Hacker News sweep.
 * Inventing them would be the one dishonest thing on the page.
 * ================================================================== */

interface Card {
  source: string;
  quote: string;
  /** Lit, with a score. The rest are the noise it was found in. */
  score?: number;
  top: string;
  left: string;
  width: number;
  rotate: number;
  /** Seconds. Staggered so nothing moves in lockstep. */
  delay: number;
  duration: number;
  /** Crowded on a phone, so most are hidden there. */
  smallScreen?: boolean;
}

const CARDS: Card[] = [
  {
    source: "news.ycombinator.com",
    quote: "our bill went 4x after we added history",
    score: 85,
    top: "16%",
    left: "6%",
    width: 268,
    rotate: -1.5,
    delay: 0,
    duration: 26,
    smallScreen: true,
  },
  {
    source: "github · topoteretes/cognee",
    quote:
      "re-asking the identical question after the delete returns the cached pre-delete answer verbatim",
    score: 71,
    top: "56%",
    left: "68%",
    width: 296,
    rotate: 1.2,
    delay: 3,
    duration: 30,
    smallScreen: true,
  },
  {
    source: "github · langchain-ai/langchain",
    quote:
      "every chunk after the first batch is treated as 'not found' and then deleted + embedded",
    top: "8%",
    left: "63%",
    width: 280,
    rotate: 2,
    delay: 1.5,
    duration: 34,
  },
  {
    source: "github · mem0ai/mem0",
    quote:
      "contradictory memories accumulate over time instead of the newer fact superseding the older one",
    top: "70%",
    left: "4%",
    width: 272,
    rotate: -2.2,
    delay: 5,
    duration: 28,
  },
  {
    source: "github · run-llama/llama_index",
    quote: "the document disappears from the index entirely",
    top: "38%",
    left: "1%",
    width: 224,
    rotate: 1,
    delay: 7,
    duration: 32,
  },
  {
    source: "github · deepset-ai/haystack",
    quote: "most resulting chunks are identical to the previous run",
    top: "84%",
    left: "58%",
    width: 250,
    rotate: -1,
    delay: 2,
    duration: 27,
  },
  {
    source: "github · langchain-ai/langgraph",
    quote: "the old vector for doc1 remains in _vectors",
    top: "27%",
    left: "78%",
    width: 218,
    rotate: -2.5,
    delay: 6,
    duration: 31,
  },
  // Noise, on purpose. What the filters throw away is half the story.
  {
    source: "github · dependabot",
    quote: "bump lodash from 4.17.20 to 4.17.21",
    top: "48%",
    left: "84%",
    width: 200,
    rotate: 2.8,
    delay: 4,
    duration: 24,
  },
  {
    source: "github · stale-bot",
    quote: "This issue is stale and will be closed in 7 days",
    top: "78%",
    left: "31%",
    width: 226,
    rotate: 1.6,
    delay: 8,
    duration: 29,
  },
  {
    source: "news.ycombinator.com",
    quote: "Show HN: I rebuilt my blog in Rust and it loads in 4ms",
    top: "5%",
    left: "30%",
    width: 232,
    rotate: -1.8,
    delay: 2.5,
    duration: 33,
  },
];

export default function ConversationField() {
  const theme = useTheme();
  const dark = theme.palette.mode === "dark";

  return (
    <Box
      aria-hidden
      sx={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        // Decoration. It must never eat a click meant for the form.
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      {CARDS.map((card) => {
        const lit = card.score !== undefined;
        return (
          <Box
            key={card.quote}
            sx={{
              position: "absolute",
              top: card.top,
              left: card.left,
              width: card.width,
              maxWidth: "44vw",
              p: 1.75,
              borderRadius: 2,
              border: 1,
              borderColor: lit
                ? alpha(theme.palette.primary.main, dark ? 0.55 : 0.4)
                : "divider",
              bgcolor: lit
                ? alpha(theme.palette.primary.main, dark ? 0.1 : 0.05)
                : "background.paper",
              // Noise sits back; the found ones step forward. No other
              // device on the page carries this idea.
              opacity: lit ? (dark ? 0.92 : 0.98) : dark ? 0.3 : 0.5,
              boxShadow: lit
                ? `0 18px 40px -28px ${alpha(theme.palette.primary.main, 0.9)}`
                : "none",
              display: {
                xs: card.smallScreen ? "block" : "none",
                md: "block",
              },
              "@keyframes drift": {
                from: { transform: `translateY(10px) rotate(${card.rotate}deg)` },
                to: { transform: `translateY(-10px) rotate(${card.rotate}deg)` },
              },
              transform: `rotate(${card.rotate}deg)`,
              animation: `drift ${card.duration}s ease-in-out ${card.delay}s infinite alternate`,
              "@media (prefers-reduced-motion: reduce)": { animation: "none" },
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
              <Typography
                sx={{
                  fontFamily: MONO,
                  fontSize: 10,
                  letterSpacing: ".06em",
                  color: "text.secondary",
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {card.source}
              </Typography>
              {lit && (
                <Chip
                  size="small"
                  color="primary"
                  label={card.score}
                  sx={{
                    height: 19,
                    fontFamily: MONO,
                    fontSize: 11,
                    fontWeight: 700,
                    "& .MuiChip-label": { px: 0.9 },
                  }}
                />
              )}
            </Box>
            <Typography
              sx={{
                fontSize: 12.5,
                lineHeight: 1.5,
                color: lit ? "text.primary" : "text.secondary",
                fontStyle: "italic",
              }}
            >
              “{card.quote}”
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}
