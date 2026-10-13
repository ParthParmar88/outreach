import { useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import SearchIcon from "@mui/icons-material/Search";

import { ErrorBlock, Loading } from "@/components/StateBlocks";
import { platformIcon } from "@/features/plan/platformIcon";
import { activityApi, type Activity } from "@/lib/activityApi";
import { trackingApi } from "@/lib/trackingApi";
import { useSelectedProduct } from "@/lib/selectedProduct";
import { MONO } from "@/styles/theme";

/**
 * What outreach did for you, across every product.
 *
 * Three numbers carry the screen: what the search found, what you wrote
 * back, and what you actually sent. Everything else on the page exists to
 * stop those three being read as more than they are.
 */
export default function ActivityRoute() {
  const { selected, products, loading: loadingProducts } = useSelectedProduct();

  const [data, setData] = useState<Activity | null>(null);
  const [error, setError] = useState<string | null>(null);
  /* One product, or all of them. Defaults to the product in the top bar,
     because that is the one you were just looking at - opening Activity
     should answer "how is *this* going", not hand you a total that mixes
     one product's numbers into another's. */
  const [everything, setEverything] = useState(false);

  const productId = everything ? undefined : selected?.id;

  useEffect(() => {
    // Wait for the switcher rather than firing an account-wide call first
    // and a product-scoped one a moment later, which makes the numbers
    // visibly jump.
    if (!everything && !selected) return;

    let cancelled = false;
    const fetchActivity = () =>
      activityApi
        .get(productId)
        .then((found) => !cancelled && setData(found))
        .catch((e: unknown) =>
          !cancelled && setError(e instanceof Error ? e.message : String(e)),
        );

    setData(null);
    void fetchActivity();

    // "Answered" only moves when somebody looks at the threads again. Shown
    // straight away with what is known, then refreshed if the look changed
    // anything; a failed check leaves the numbers as they were.
    trackingApi
      .checkReplies(productId)
      .then((result) => {
        if (result.changed > 0) void fetchActivity();
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [productId, everything, selected]);

  if (error) {
    return (
      <Page>
        <ErrorBlock message={error} onRetry={() => window.location.reload()} />
      </Page>
    );
  }

  /* No products at all. Said here rather than left to the loader, because
     with nothing selected the fetch above never runs - and a spinner that
     spins forever is the worst way to say "you have not added anything". */
  if (!loadingProducts && products.length === 0) {
    return (
      <Page>
        <Paper variant="outlined" sx={{ px: 3, py: 7, textAlign: "center" }}>
          <Typography sx={{ fontWeight: 650, fontSize: 18, mb: 1 }}>
            Nothing to measure yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Add a product, run a search, and this screen fills in on its own.
          </Typography>
          <Button component={RouterLink} to="/new" variant="contained">
            Add a product
          </Button>
        </Paper>
      </Page>
    );
  }

  if (!data) {
    return (
      <Page>
        <Loading label="Adding it up" />
      </Page>
    );
  }

  const { totals, outcomes } = data;
  const nothingYet = totals.searches === 0 && totals.written === 0;
  const judged = Object.values(outcomes).reduce((sum, n) => sum + (n ?? 0), 0);

  return (
    <Page>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", sm: "flex-end" }}
        gap={2}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="overline"
            sx={{ color: "text.secondary", letterSpacing: ".16em", fontSize: 10.5 }}
          >
            Activity
          </Typography>
          <Typography
            variant="h4"
            sx={{ fontSize: { xs: 24, md: 30 }, fontWeight: 680, letterSpacing: "-.022em" }}
          >
            {/* The product's own name, so two tabs open side by side are
                never mistaken for each other. */}
            {data.product ? data.product.name : "All your products"}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: "68ch" }}>
            {data.product ? (
              <>
                What outreach did for <b>{data.product.domain}</b>, and where it
                happened. Switch product in the bar above.
              </>
            ) : (
              <>
                Everything across all {data.products}{" "}
                {data.products === 1 ? "product" : "products"} added together.
              </>
            )}
          </Typography>
        </Box>

        {/* Only offered when there is more than one product to add up. */}
        {products.length > 1 && (
          <ToggleButtonGroup
            size="small"
            exclusive
            value={everything ? "all" : "one"}
            onChange={(_, next) => next && setEverything(next === "all")}
            sx={{ flexShrink: 0 }}
          >
            <ToggleButton value="one" sx={{ px: 1.75, textTransform: "none" }}>
              This product
            </ToggleButton>
            <ToggleButton value="all" sx={{ px: 1.75, textTransform: "none" }}>
              All
            </ToggleButton>
          </ToggleButtonGroup>
        )}
      </Stack>

      {nothingYet ? (
        <Paper variant="outlined" sx={{ px: 3, py: 7, textAlign: "center" }}>
          <SearchIcon sx={{ fontSize: 28, color: "text.disabled", mb: 1.5 }} />
          <Typography sx={{ fontWeight: 650, fontSize: 18, mb: 1 }}>
            Nothing to show yet
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: "48ch", mx: "auto", mb: 3 }}
          >
            {data.product ? (
              <>
                Nothing has been searched for <b>{data.product.name}</b> yet.
                Other products may have activity of their own — switch in the
                bar above, or press All.
              </>
            ) : (
              <>Run a search on a product and this fills in on its own.</>
            )}
          </Typography>
          {/* Straight to the search for the product on screen, rather than
              back to a list they would have to pick out of again. */}
          <Button
            component={RouterLink}
            to={
              data.product
                ? `/opportunities?product=${data.product.id}&new=1`
                : "/home"
            }
            variant="contained"
            startIcon={<SearchIcon />}
          >
            {data.product ? `Search for ${data.product.name}` : "Go to your products"}
          </Button>
        </Paper>
      ) : (
        <>
          {/* The three numbers, in the order they happen. */}
          <Box
            sx={{
              display: "grid",
              gap: 2,
              gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" },
            }}
          >
            <BigNumber
              value={totals.results}
              label="People found"
              says={`from ${totals.searches} ${totals.searches === 1 ? "search" : "searches"}`}
            />
            <BigNumber
              value={totals.written}
              label="Replies written"
              says="posts you judged worth answering"
            />
            <BigNumber
              value={totals.posted}
              label="Replies sent"
              says="you posted these yourself"
              accent
            />
          </Box>

          {/* Where it happened. The table is the answer to "and Reddit?" */}
          <Box component="section">
            <Typography sx={{ fontWeight: 680, fontSize: 19, mb: 0.5 }}>
              By platform
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Platforms marked &ldquo;not connected&rdquo; are listed anyway, so
              a zero there reads as &ldquo;not built yet&rdquo; rather than
              &ldquo;nobody is talking about you there&rdquo;.
            </Typography>

            <Paper variant="outlined" sx={{ overflowX: "auto" }}>
              <Table size="small" sx={{ minWidth: 620 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Platform</TableCell>
                    <Head>Searches</Head>
                    <Head>People found</Head>
                    <Head>Replies written</Head>
                    <Head>Sent</Head>
                    <Head>Answered</Head>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.platforms.map((row) => {
                    const Icon = platformIcon(row.key, row.name);
                    const used = row.searches > 0 || row.written > 0;
                    return (
                      <TableRow key={row.key} hover>
                        <TableCell>
                          <Stack direction="row" alignItems="center" gap={1.25}>
                            <Icon
                              sx={{
                                fontSize: 18,
                                color: used ? "text.primary" : "text.disabled",
                              }}
                            />
                            <Typography sx={{ fontSize: 14, fontWeight: used ? 620 : 400 }}>
                              {row.name}
                            </Typography>
                            {!row.connected && (
                              <Chip
                                size="small"
                                label="not connected"
                                variant="outlined"
                                sx={{ height: 19, fontSize: 10 }}
                              />
                            )}
                          </Stack>
                        </TableCell>
                        <Num value={row.searches} />
                        <Num value={row.results} />
                        <Num value={row.written} />
                        <Num value={row.posted} />
                        <Num value={row.answered} />
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Paper>
          </Box>

          {/* The honest paragraph. Without it the three numbers above read
              as achievement, and two of them are only activity. */}
          <Paper
            variant="outlined"
            sx={{ p: 2.5, borderLeft: 3, borderLeftColor: "primary.main" }}
          >
            <Typography sx={{ fontWeight: 650, fontSize: 15, mb: 0.75 }}>
              What these numbers are worth
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "70ch" }}>
              {judged === 0 ? (
                <>
                  <b>People found</b> and <b>replies written</b> say what the tool
                  did. <b>Replies sent</b> says what you did. None of the three
                  says whether it was worth it — that only appears once you mark
                  what came of a reply, on a product&rsquo;s Tracking tab.
                </>
              ) : (
                <>
                  {judged} of your {totals.posted} sent{" "}
                  {totals.posted === 1 ? "reply has" : "replies have"} an outcome
                  recorded. That is the only number here you could defend to
                  anyone — the rest is activity.
                </>
              )}
            </Typography>

            {judged > 0 && (
              <Stack direction="row" gap={1} sx={{ mt: 1.75 }} flexWrap="wrap">
                {(["customer", "lead", "conversation", "ignored"] as const).map((key) =>
                  outcomes[key] ? (
                    <Chip
                      key={key}
                      label={`${outcomes[key]} ${key}`}
                      size="small"
                      variant="outlined"
                      color={
                        key === "customer" || key === "lead" ? "success" : "default"
                      }
                    />
                  ) : null,
                )}
              </Stack>
            )}
          </Paper>
        </>
      )}
    </Page>
  );
}

/* ------------------------------------------------------------------ */

function Page({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ maxWidth: 940, mx: "auto", px: { xs: 2, sm: 3 }, py: { xs: 3, md: 5 } }}>
      <Stack gap={3.5}>{children}</Stack>
    </Box>
  );
}

function BigNumber({
  value,
  label,
  says,
  accent = false,
}: {
  value: number;
  label: string;
  says: string;
  accent?: boolean;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography
        sx={{
          fontFamily: MONO,
          fontSize: 40,
          fontWeight: 600,
          lineHeight: 1,
          fontVariantNumeric: "tabular-nums",
          color: value === 0 ? "text.disabled" : accent ? "primary.main" : "text.primary",
        }}
      >
        {value.toLocaleString()}
      </Typography>
      <Typography sx={{ fontWeight: 650, fontSize: 15, mt: 1 }}>{label}</Typography>
      <Typography variant="caption" color="text.secondary">
        {says}
      </Typography>
    </Paper>
  );
}

function Head({ children }: { children: ReactNode }) {
  return (
    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
      {children}
    </TableCell>
  );
}

function Num({ value }: { value: number }) {
  return (
    <TableCell
      align="right"
      sx={{
        fontFamily: MONO,
        fontVariantNumeric: "tabular-nums",
        color: value === 0 ? "text.disabled" : "text.primary",
      }}
    >
      {value}
    </TableCell>
  );
}
