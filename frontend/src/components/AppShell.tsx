import { useState, type ReactNode } from "react";
import { Link as RouterLink, useLocation, useNavigate } from "react-router-dom";

import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import AddIcon from "@mui/icons-material/Add";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import LogoutIcon from "@mui/icons-material/LogoutOutlined";

import ProductSwitcher from "./ProductSwitcher";
import { hairline } from "./ui";
import { useAuth } from "@/lib/auth";

interface Props {
  mode: "light" | "dark";
  onToggleMode: () => void;
  children: ReactNode;
}

const NAV = [
  { to: "/home", label: "Home" },
  // Account-wide, not per product: "is this tool worth the time" is not a
  // question any single product can answer.
  { to: "/activity", label: "Activity" },
  { to: "/settings/product", label: "Products" },
];

export default function AppShell({ mode, onToggleMode, children }: Props) {
  const { user, logOut } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const initials = (user?.name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  const signOut = async () => {
    setAnchor(null);
    await logOut();
    navigate("/", { replace: true });
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      {/* A plain Box, not an AppBar.
          AppBar brings a colour scheme, an elevation model and a z-index
          that all have to be argued back out of it before anything can be
          styled. Sticky plus a border is the whole of what was wanted. */}
      <Box
        component="header"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: (t) => t.zIndex.appBar,
          borderBottom: 1,
          borderColor: (t) => hairline(t),
          // Frosted rather than solid. The page scrolling *under* the bar
          // instead of behind an opaque slab is most of what makes a header
          // feel like an application chrome rather than a table row.
          bgcolor: (t) => alpha(t.palette.background.paper, 0.82),
          backdropFilter: "blur(14px) saturate(180%)",
          WebkitBackdropFilter: "blur(14px) saturate(180%)",
        }}
      >
        <Box
          sx={{
            maxWidth: 1400,
            mx: "auto",
            px: { xs: 2, sm: 3 },
            height: 62,
            display: "flex",
            alignItems: "center",
            gap: { xs: 1, md: 2 },
          }}
        >
          {/* ------------------------------------------------- identity */}
          <Stack
            direction="row"
            alignItems="center"
            gap={1.25}
            component={RouterLink}
            to="/home"
            sx={{ textDecoration: "none", color: "text.primary", flexShrink: 0 }}
          >
            <Logo />
            <Typography
              sx={{
                fontWeight: 720,
                fontSize: 16,
                letterSpacing: "-.03em",
                display: { xs: "none", sm: "block" },
              }}
            >
              Outreach
            </Typography>
          </Stack>

          {/* Everything else sits to the right of this. */}
          <Box sx={{ flex: 1 }} />

          {/* Which product you are on, first in the right-hand group.
              Before the links rather than after, because it is the context
              they are read in - the switcher says *what* you are looking at
              and the links say *which view of it*. */}
          <ProductSwitcher />

          {/* ----------------------------------------------- navigation */}
          <Stack direction="row" gap={0.5} sx={{ display: { xs: "none", md: "flex" } }}>
            {NAV.map((item) => {
              const active = pathname === item.to;
              return (
                <Button
                  key={item.to}
                  component={RouterLink}
                  to={item.to}
                  size="small"
                  disableRipple
                  sx={{
                    px: 1.75,
                    color: active ? "text.primary" : "text.secondary",
                    fontWeight: active ? 650 : 560,
                    bgcolor: (t) =>
                      active ? alpha(t.palette.text.primary, 0.06) : "transparent",
                    "&:hover": {
                      bgcolor: (t) => alpha(t.palette.text.primary, 0.045),
                      color: "text.primary",
                    },
                  }}
                >
                  {item.label}
                </Button>
              );
            })}
          </Stack>

          <Button
            component={RouterLink}
            to="/new"
            size="small"
            variant="contained"
            startIcon={<AddIcon sx={{ fontSize: 17 }} />}
            sx={{ flexShrink: 0, ml: { xs: 0, md: 1 } }}
          >
            <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
              New product
            </Box>
            <Box component="span" sx={{ display: { xs: "inline", sm: "none" } }}>
              New
            </Box>
          </Button>

          <Box
            sx={{
              width: "1px",
              height: 22,
              bgcolor: (t) => hairline(t),
              mx: 0.75,
              display: { xs: "none", sm: "block" },
            }}
          />

          {/* -------------------------------------------------- account */}
          <Tooltip title={mode === "light" ? "Dark theme" : "Light theme"}>
            <IconButton
              size="small"
              onClick={onToggleMode}
              sx={{ color: "text.secondary", flexShrink: 0 }}
            >
              {mode === "light" ? (
                <DarkModeOutlinedIcon sx={{ fontSize: 19 }} />
              ) : (
                <LightModeOutlinedIcon sx={{ fontSize: 19 }} />
              )}
            </IconButton>
          </Tooltip>

          <Tooltip title={user?.name ?? "Account"}>
            <IconButton
              size="small"
              onClick={(e) => setAnchor(e.currentTarget)}
              sx={{ p: 0.5, flexShrink: 0 }}
            >
              <Avatar
                sx={{
                  width: 30,
                  height: 30,
                  fontSize: 12,
                  fontWeight: 700,
                  color: "primary.contrastText",
                  backgroundImage: (t) =>
                    `linear-gradient(140deg, ${t.palette.primary.light}, ${t.palette.primary.dark})`,
                }}
              >
                {initials}
              </Avatar>
            </IconButton>
          </Tooltip>

          <Menu
            anchorEl={anchor}
            open={Boolean(anchor)}
            onClose={() => setAnchor(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            slotProps={{ paper: { sx: { minWidth: 232, mt: 1 } } }}
          >
            <Box sx={{ px: 2, py: 1.25 }}>
              <ListItemText
                primary={user?.name}
                secondary={user?.email}
                slotProps={{
                  primary: { fontWeight: 650, fontSize: 14 },
                  secondary: { fontSize: 12 },
                }}
              />
            </Box>
            <Divider sx={{ my: 0.5 }} />
            <MenuItem onClick={signOut} sx={{ fontSize: 14, gap: 1.25 }}>
              <LogoutIcon sx={{ fontSize: 17, color: "text.secondary" }} />
              Sign out
            </MenuItem>
          </Menu>
        </Box>
      </Box>

      {children}
    </Box>
  );
}

/**
 * The mark.
 *
 * Drawn rather than imported: two arcs radiating from a dot, which is the
 * product in one glyph — a signal picked up from somewhere out there. A
 * wordmark on its own left the header reading as a document title.
 */
function Logo() {
  return (
    <Box
      sx={{
        width: 30,
        height: 30,
        borderRadius: 2,
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
        color: "primary.contrastText",
        backgroundImage: (t) =>
          `linear-gradient(140deg, ${t.palette.primary.light}, ${t.palette.primary.dark})`,
        boxShadow: (t) => `0 2px 8px -2px ${alpha(t.palette.primary.main, 0.55)}`,
      }}
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="7" cy="17" r="2.4" fill="currentColor" />
        <path
          d="M7 11.5a5.5 5.5 0 0 1 5.5 5.5M7 6a11 11 0 0 1 11 11"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
    </Box>
  );
}
