import { Link as RouterLink, useLocation } from "react-router-dom";

import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";

interface Props {
  productId: string;
}

/**
 * The three things you do with a product, in the order you do them.
 *
 * Plan, then search, then track what came of it. Before this the screens
 * existed but had no way between them: you reached the results from a
 * button on the plan, and the plan from a button on the home page, and
 * there was no way back at all.
 */
export default function ProductTabs({ productId }: Props) {
  const { pathname, search } = useLocation();

  const plan = `/products/${productId}/plan`;
  const tracking = `/products/${productId}/tracking`;
  // The latest search. Without `new=1` this never starts one.
  const results = `/opportunities?product=${productId}`;

  // Match on the section rather than the exact URL: the results screen
  // carries a different query string every time it runs.
  const current = pathname.endsWith("/tracking")
    ? tracking
    : pathname.startsWith("/opportunities")
      ? results
      : plan;

  return (
    <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
      <Tabs value={current} variant="scrollable" scrollButtons="auto">
        <Tab label="Marketing plan" value={plan} component={RouterLink} to={plan} />
        <Tab
          label="Opportunities"
          value={results}
          component={RouterLink}
          // Keep whatever run is on screen, so clicking the tab you are
          // already on never starts a search by accident.
          to={pathname.startsWith("/opportunities") ? `${pathname}${search}` : results}
        />
        <Tab label="Tracking" value={tracking} component={RouterLink} to={tracking} />
      </Tabs>
    </Box>
  );
}
