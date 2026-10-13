import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { productApi, type Product } from "./productApi";

const SELECTED_KEY = "outreach.selectedProduct.v1";

interface SelectedProductState {
  products: Product[];
  /** The chosen product, or null while loading and when there are none. */
  selected: Product | null;
  selectedId: string;
  /** True until the first list call answers. */
  loading: boolean;
  error: string | null;
  select: (id: string) => void;
  /** Re-fetch the list. Call after adding, deleting or re-crawling one. */
  reload: () => Promise<void>;
}

const Context = createContext<SelectedProductState | null>(null);

/**
 * Which product the whole app is looking at.
 *
 * This used to be local state on the home screen. It moved up here when the
 * switcher moved into the top bar: the bar is rendered by AppShell and the
 * screens are rendered inside it, so the two have no common ancestor to
 * share state through except a provider.
 *
 * The choice is remembered in localStorage, so coming back tomorrow reopens
 * whatever was last being worked on rather than whichever product happens
 * to be newest.
 */
export function SelectedProductProvider({ children }: { children: ReactNode }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((list: Product[]) => {
    setProducts(list);
    setSelectedId((current) => {
      // Keep the current choice when it still exists, so a reload after a
      // re-crawl does not silently move somebody to a different product.
      if (current && list.some((p) => p.id === current)) return current;

      let remembered = "";
      try {
        remembered = localStorage.getItem(SELECTED_KEY) ?? "";
      } catch {
        /* private browsing */
      }
      if (list.some((p) => p.id === remembered)) return remembered;
      return list[0]?.id ?? "";
    });
  }, []);

  const reload = useCallback(async () => {
    try {
      apply(await productApi.list());
      setError(null);
    } catch (err) {
      // A 401 here is the session expiring, which AuthProvider already
      // handles by sending the user to sign in. Anything else is worth
      // showing.
      setError(err instanceof Error ? err.message : "Could not load your products.");
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    try {
      localStorage.setItem(SELECTED_KEY, id);
    } catch {
      /* private browsing */
    }
  }, []);

  const value = useMemo<SelectedProductState>(
    () => ({
      products,
      selected: products.find((p) => p.id === selectedId) ?? null,
      selectedId,
      loading,
      error,
      select,
      reload,
    }),
    [products, selectedId, loading, error, select, reload],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSelectedProduct(): SelectedProductState {
  const value = useContext(Context);
  if (!value) {
    throw new Error("useSelectedProduct must be used inside SelectedProductProvider");
  }
  return value;
}
