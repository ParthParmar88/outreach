import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import AddIcon from "@mui/icons-material/Add";
import CheckIcon from "@mui/icons-material/Check";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";

import { hairline } from "./ui";
import { useSelectedProduct } from "@/lib/selectedProduct";
import { MONO } from "@/styles/theme";

/**
 * Which product you are working on, in the top bar.
 *
 * A Menu rather than a Select. A Select shows one line per option, and the
 * useful thing to see when switching is the domain underneath the name -
 * two products can easily be called the same thing, and their websites
 * never are.
 */
export default function ProductSwitcher() {
  const { products, selected, select, loading } = useSelectedProduct();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();

  // Nothing to switch between. The empty state on the home page is where
  // somebody is told to add one, so the bar stays quiet about it.
  if (loading || products.length === 0) return null;

  const choose = (id: string) => {
    select(id);
    setAnchor(null);
  };

  return (
    <>
      <Button
        onClick={(e) => setAnchor(e.currentTarget)}
        endIcon={<UnfoldMoreIcon sx={{ fontSize: 16, opacity: 0.6 }} />}
        color="inherit"
        sx={{
          maxWidth: { xs: 170, sm: 280 },
          py: 0.6,
          pl: 0.75,
          pr: 1.25,
          gap: 0.75,
          borderRadius: 2,
          border: 1,
          borderColor: (t) => hairline(t),
          bgcolor: "background.paper",
          "&:hover": {
            bgcolor: (t) => alpha(t.palette.text.primary, 0.04),
            borderColor: (t) => alpha(t.palette.primary.main, 0.4),
          },
        }}
      >
        {/* A monogram, so the switcher reads as a thing you own rather than
            as a dropdown. Two products with similar names are told apart by
            colour before either is read. */}
        <Box
          sx={{
            width: 24,
            height: 24,
            flexShrink: 0,
            borderRadius: 1.5,
            display: "grid",
            placeItems: "center",
            fontSize: 11,
            fontWeight: 800,
            color: "primary.main",
            border: 1,
            borderColor: (t) => alpha(t.palette.primary.main, 0.3),
            bgcolor: (t) => alpha(t.palette.primary.main, 0.12),
          }}
        >
          {(selected?.name ?? "?").slice(0, 1).toUpperCase()}
        </Box>
        <Box sx={{ minWidth: 0, textAlign: "left" }}>
          <Typography
            sx={{ fontWeight: 660, fontSize: 13.5, lineHeight: 1.3, letterSpacing: "-.01em" }}
            noWrap
          >
            {selected?.name ?? "Choose a product"}
          </Typography>
          {selected && (
            <Typography
              sx={{
                fontFamily: MONO,
                fontSize: 10.5,
                lineHeight: 1.3,
                color: "text.secondary",
              }}
              noWrap
            >
              {selected.domain}
            </Typography>
          )}
        </Box>
      </Button>

      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{ paper: { sx: { minWidth: 296, maxWidth: 400, mt: 1 } } }}
      >
        {products.map((product) => (
          <MenuItem
            key={product.id}
            selected={product.id === selected?.id}
            onClick={() => choose(product.id)}
          >
            <Box
              sx={{
                width: 16,
                mr: 1.25,
                flexShrink: 0,
                display: "flex",
                color: "primary.main",
              }}
            >
              {product.id === selected?.id && <CheckIcon sx={{ fontSize: 16 }} />}
            </Box>
            <ListItemText
              primary={
                <Stack direction="row" alignItems="center" gap={1}>
                  <Box component="span" sx={{ fontWeight: 620 }}>
                    {product.name}
                  </Box>
                  {product.state !== "ready" && (
                    <Chip
                      size="small"
                      label={product.state}
                      variant="outlined"
                      sx={{ height: 18, fontSize: 10 }}
                    />
                  )}
                </Stack>
              }
              secondary={product.domain}
              slotProps={{
                primary: { fontSize: 14 },
                secondary: { fontSize: 11.5, fontFamily: MONO },
              }}
            />
          </MenuItem>
        ))}

        <Divider />
        <MenuItem
          onClick={() => {
            setAnchor(null);
            navigate("/new");
          }}
        >
          <Box sx={{ width: 16, mr: 1.25, display: "flex", color: "text.secondary" }}>
            <AddIcon sx={{ fontSize: 16 }} />
          </Box>
          <Typography sx={{ fontSize: 14 }}>New product</Typography>
        </MenuItem>
      </Menu>
    </>
  );
}
