import { createTheme, type Theme } from "@mui/material/styles";

/**
 * One theme, two colour schemes. Every colour in the app comes from here.
 * No component hard-codes a hex value.
 *
 * ── Why the backgrounds are the way they are ─────────────────────────────
 *
 * The single biggest thing separating a product from a page of default
 * components is whether surfaces sit on *layers*. Light mode used to put
 * near-white cards on a mid-grey wash, which reads as an unstyled document
 * however carefully the insides are arranged. The ground is now a soft warm
 * grey and cards are pure white, so a card looks lifted rather than merely
 * outlined. Dark mode does the same in reverse and keeps a blue-black cast
 * rather than pure black, which stops large fills looking like holes.
 */
export function createAppTheme(mode: "light" | "dark"): Theme {
  const light = {
    // Deeper and slightly cooler than before. The old green read as
    // municipal; this one holds up next to white without going muddy.
    primary: { main: "#116B54", light: "#1C8A6E", dark: "#0B4A3A", contrastText: "#FFFFFF" },
    secondary: { main: "#7A4A1E", contrastText: "#FFFFFF" },
    background: { default: "#F4F6F8", paper: "#FFFFFF" },
    text: { primary: "#0B1219", secondary: "#5A6875", disabled: "#93A0AC" },
    divider: "#E2E8EE",
    success: { main: "#0C7A55" },
    warning: { main: "#8A5A08" },
    error: { main: "#B03A3A" },
    info: { main: "#24558C" },
  };

  const dark = {
    primary: { main: "#3FBF9B", light: "#63D2B4", dark: "#2A9C7D", contrastText: "#04201A" },
    secondary: { main: "#D0A366", contrastText: "#1B1307" },
    // Not #000. A pure black ground makes every card edge a cliff and
    // every large fill a hole; a blue-black keeps depth readable.
    background: { default: "#0A0E14", paper: "#141A22" },
    text: { primary: "#ECF1F6", secondary: "#98A6B4", disabled: "#67757F" },
    divider: "#252F3B",
    success: { main: "#48C79A" },
    warning: { main: "#DFA855" },
    error: { main: "#F08287" },
    info: { main: "#82ACDF" },
  };

  const palette = mode === "light" ? light : dark;

  return createTheme({
    palette: { mode, ...palette },
    // 10px. Eight looked utilitarian and sixteen looked like a toy; this is
    // the radius almost every current product settles on.
    shape: { borderRadius: 10 },
    typography: {
      fontFamily:
        '"Inter var","Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif',
      // Negative tracking on the big sizes only. Applying it to body text
      // is the usual way a page ends up feeling cramped rather than crisp.
      h4: { fontWeight: 700, letterSpacing: "-0.03em" },
      h5: { fontWeight: 690, letterSpacing: "-0.025em" },
      h6: { fontWeight: 680, letterSpacing: "-0.018em" },
      subtitle2: { fontWeight: 620, fontSize: 13.5 },
      body2: { fontSize: 13.5, lineHeight: 1.65 },
      caption: { fontSize: 12, lineHeight: 1.55 },
      button: { textTransform: "none", fontWeight: 620, letterSpacing: "-0.005em" },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: { WebkitFontSmoothing: "antialiased" },
          // Scrollbars are part of the surface. Left alone they are the one
          // piece of raw operating system on an otherwise designed page.
          "*::-webkit-scrollbar": { width: 11, height: 11 },
          "*::-webkit-scrollbar-thumb": {
            borderRadius: 8,
            border: "3px solid transparent",
            backgroundClip: "content-box",
            backgroundColor: mode === "light" ? "#C8D2DC" : "#2C3846",
          },
          "*::-webkit-scrollbar-thumb:hover": {
            backgroundColor: mode === "light" ? "#AEBCC9" : "#3A4857",
          },
        },
      },
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
      MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: 10 },
          // A focus ring rather than a thicker border, so nothing reflows
          // by a pixel when a field is focused.
          notchedOutline: { transition: "border-color .18s ease" },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            borderRadius: 10,
            paddingInline: 18,
            paddingBlock: 8,
            transition: "background-color .18s ease, border-color .18s ease, transform .12s ease",
            "&:active": { transform: "translateY(1px)" },
          },
          containedPrimary: {
            // A hairline of the darker tone along the bottom. It is what
            // stops a flat fill reading as a coloured rectangle.
            boxShadow: `inset 0 -1px 0 ${mode === "light" ? "rgba(0,0,0,.18)" : "rgba(0,0,0,.28)"}`,
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: 7, fontWeight: 560 },
          label: { paddingInline: 10 },
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: {
            borderRadius: 12,
            border: `1px solid ${palette.divider}`,
            boxShadow:
              mode === "light"
                ? "0 4px 6px -2px rgba(11,18,25,.05), 0 16px 40px -8px rgba(11,18,25,.16)"
                : "0 4px 6px -2px rgba(0,0,0,.4), 0 16px 40px -8px rgba(0,0,0,.6)",
          },
        },
      },
      MuiMenuItem: { styleOverrides: { root: { borderRadius: 8, marginInline: 6 } } },
      MuiTooltip: {
        styleOverrides: {
          tooltip: { borderRadius: 8, fontSize: 12, paddingBlock: 6, paddingInline: 10 },
        },
      },
      MuiAlert: { styleOverrides: { root: { borderRadius: 10 } } },
      MuiFormHelperText: {
        styleOverrides: { root: { marginLeft: 0, marginTop: 6, lineHeight: 1.5 } },
      },
    },
  });
}

/** Used wherever digits have to line up or a hash is shown. */
export const MONO = '"Cascadia Mono",Consolas,ui-monospace,"SF Mono",monospace';
