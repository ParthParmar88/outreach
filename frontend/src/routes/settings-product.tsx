import { useCallback, useEffect, useRef, useState } from "react";

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { Loading, PageHeader } from "@/components/StateBlocks";
import { Surface } from "@/components/ui";
import MarkdownDialog from "@/features/product/MarkdownDialog";
import ProductCard from "@/features/product/ProductCard";
import ProductForm from "@/features/product/ProductForm";
import { isRunning, productApi, type Product } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

const POLL_MS = 1500;

/**
 * Product websites.
 *
 * The one screen that talks to the real backend. Everything else in the app
 * is still on sample data, because briefs, plans and runs have no service
 * behind them yet.
 */
export default function SettingsProductRoute() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [viewing, setViewing] = useState<Product | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const timer = useRef<number | undefined>(undefined);

  const refresh = useCallback(async (): Promise<Product[]> => {
    const list = await productApi.list();
    setProducts(list);
    return list;
  }, []);

  /* Poll only while something is actually crawling. A finished list sits
     still, rather than hammering the server for no reason. */
  const scheduleIfBusy = useCallback(
    (list: Product[]) => {
      window.clearTimeout(timer.current);
      if (!list.some(isRunning)) return;
      timer.current = window.setTimeout(() => {
        void refresh().then(scheduleIfBusy).catch(() => undefined);
      }, POLL_MS);
    },
    [refresh],
  );

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const up = await productApi.isBackendUp();
      if (cancelled) return;
      setBackendUp(up);
      if (!up) {
        setProducts([]);
        return;
      }
      try {
        const list = await refresh();
        if (!cancelled) scheduleIfBusy(list);
      } catch {
        if (!cancelled) setProducts([]);
      }
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(timer.current);
    };
  }, [refresh, scheduleIfBusy]);

  const create = async (name: string, url: string) => {
    await productApi.create({ name, url });
    setToast(`Reading ${url}. This takes anywhere from ten seconds to a few minutes.`);
    scheduleIfBusy(await refresh());
  };

  const recrawl = async (product: Product) => {
    setBusyId(product.id);
    try {
      await productApi.recrawl(product.id);
      setToast(`Reading ${product.domain} again.`);
      scheduleIfBusy(await refresh());
    } catch (err) {
      setToast(err instanceof Error ? err.message : "Could not start it again.");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (product: Product) => {
    if (!window.confirm(`Delete ${product.name} and everything we read for it?`)) return;
    setBusyId(product.id);
    try {
      await productApi.remove(product.id);
      setToast(`${product.name} deleted.`);
      await refresh();
    } catch (err) {
      setToast(err instanceof Error ? err.message : "Could not delete it.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto", px: { xs: 2, sm: 3 }, py: { xs: 3, md: 4.5 } }}>
      <PageHeader eyebrow="Settings" title="Product websites">
        Give us a product and its website. We read the site once and keep it as one
        markdown document. It is never re-read on a schedule, only when you press
        Read again.
      </PageHeader>

      {backendUp === false && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <AlertTitle>The backend is not running</AlertTitle>
          This is the one screen that needs a real server. Start it in a second
          terminal:
          <Box
            component="pre"
            sx={{ fontFamily: MONO, fontSize: 12, mt: 1, mb: 0, whiteSpace: "pre-wrap" }}
          >
            {"cd backend\n.venv\\Scripts\\python.exe -m uvicorn outreach.main:app --reload"}
          </Box>
        </Alert>
      )}

      {backendUp && (
        <Box sx={{ mb: 3 }}>
          <ProductForm disabled={false} onSubmit={create} />
        </Box>
      )}

      {backendUp === null || products === null ? (
        <Loading label="Checking the backend" />
      ) : products.length === 0 && backendUp ? (
        <Surface sx={{ px: 3, py: { xs: 6, md: 8 }, textAlign: "center" }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            No websites read yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "44ch", mx: "auto" }}>
            Add a product above. Try your own first, so you can judge whether what
            comes back really describes it.
          </Typography>
        </Surface>
      ) : (
        <Stack spacing={2}>
          {products.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              busy={busyId === product.id}
              onView={setViewing}
              onRecrawl={recrawl}
              onDelete={remove}
            />
          ))}
        </Stack>
      )}

      <MarkdownDialog product={viewing} onClose={() => setViewing(null)} />

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}
