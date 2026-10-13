import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Loading } from "@/components/StateBlocks";
import { authApi, type User } from "./authApi";

interface AuthState {
  user: User | null;
  /** True until the first /auth/me answers. Nothing may redirect before then. */
  loading: boolean;
  signUp: (name: string, email: string, password: string) => Promise<void>;
  logIn: (email: string, password: string) => Promise<void>;
  logOut: () => Promise<void>;
  /** Re-read the session, for anything that signs in without these forms. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // One call on load. The cookie is httpOnly, so asking the server is the
  // only way to know whether anybody is signed in.
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((found) => !cancelled && setUser(found))
      .catch(() => !cancelled && setUser(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  /*
   * A session can expire while somebody is using the app. Without this, the
   * next call fails and the screen shows a red "Not signed in." box that the
   * user can do nothing about, on a page that still looks signed in.
   *
   * The API layer raises this event on any 401. An event rather than an
   * import, so the api modules stay free of React and there is no cycle.
   */
  useEffect(() => {
    const onUnauthorised = () => setUser(null);
    window.addEventListener("outreach:unauthorised", onUnauthorised);
    return () => window.removeEventListener("outreach:unauthorised", onUnauthorised);
  }, []);

  const signUp = useCallback(async (name: string, email: string, password: string) => {
    setUser(await authApi.signUp(name, email, password));
  }, []);

  const logIn = useCallback(async (email: string, password: string) => {
    setUser(await authApi.logIn(email, password));
  }, []);

  const logOut = useCallback(async () => {
    try {
      await authApi.logOut();
    } finally {
      // Sign out locally even if the request failed. Leaving somebody
      // apparently signed in after they asked to leave is the worse failure.
      setUser(null);
    }
  }, []);

  /* Re-read the session from the server.
   *
   * For the paths that get signed in by something other than the two forms
   * above - a password reset sets the cookie in its own response, and
   * without this the app still believes nobody is signed in and bounces
   * straight back to the login page. */
  const refresh = useCallback(async () => {
    setUser(await authApi.me());
  }, []);

  const value = useMemo(
    () => ({ user, loading, signUp, logIn, logOut, refresh }),
    [user, loading, signUp, logIn, logOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}

/**
 * Wraps the routes that need an account.
 *
 * Waits for the first /auth/me before deciding. Redirecting while still
 * loading would bounce a signed-in person to the login page on every hard
 * refresh, which looks exactly like being logged out at random.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading label="Checking your session" />;

  if (!user) {
    // Remember where they were headed, so signing in continues the journey
    // instead of dumping them on a home screen. `reason` is what stops this
    // reading as the app randomly throwing you out: the login page says why
    // you are looking at it.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname, reason: "signed-out" }}
      />
    );
  }

  return <>{children}</>;
}
