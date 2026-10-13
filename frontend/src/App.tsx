import { useMemo, useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";

import AppShell from "@/components/AppShell";
import ActivityRoute from "@/routes/activity";
import ForgotPasswordRoute from "@/routes/forgot-password";
import ResetPasswordRoute from "@/routes/reset-password";
import { AuthProvider, RequireAuth } from "@/lib/auth";
import { SelectedProductProvider } from "@/lib/selectedProduct";
import BriefsRoute from "@/routes/briefs";
import HomeRoute from "@/routes/home";
import LandingRoute from "@/routes/landing";
import LoginRoute from "@/routes/login";
import NewProductRoute from "@/routes/new-search";
import OpportunitiesRoute from "@/routes/opportunities";
import PlanRoute from "@/routes/plan";
import ReadingWebsiteRoute from "@/routes/reading-website";
import ResultsRoute from "@/routes/results";
import ReviewPlanRoute from "@/routes/review-plan";
import RunRoute from "@/routes/run";
import SettingsProductRoute from "@/routes/settings-product";
import SignUpRoute from "@/routes/signup";
import TrackingRoute from "@/routes/tracking";
import { createAppTheme } from "@/styles/theme";

type Mode = "light" | "dark";

/**
 * Three layouts.
 *
 *   public   the landing page, sign up and sign in. Full bleed, no chrome,
 *            nowhere to navigate except forward.
 *   private  everything else, inside the app shell and behind RequireAuth.
 *
 * The flow is: landing -> sign up -> new product -> read the website.
 * Returning users land on /home and pick a product they already made.
 */
export default function App() {
  const [mode, setMode] = useState<Mode>(() =>
    window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  );

  const theme = useMemo(() => createAppTheme(mode), [mode]);
  const toggle = () => setMode(mode === "light" ? "dark" : "light");

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* ---------------------------------------------- public */}
            <Route path="/" element={<LandingRoute mode={mode} onToggleMode={toggle} />} />
            <Route path="/signup" element={<SignUpRoute />} />
            <Route path="/login" element={<LoginRoute />} />
            {/* Public by necessity: somebody who cannot sign in is exactly
                who these two screens are for. */}
            <Route path="/forgot-password" element={<ForgotPasswordRoute />} />
            <Route path="/reset-password" element={<ResetPasswordRoute />} />

            {/* ---------------------------------------------- private */}
            {/* The provider sits inside RequireAuth, so the product list is
                only ever fetched for somebody who is signed in. */}
            <Route
              element={
                <RequireAuth>
                  <SelectedProductProvider>
                    <AppShell mode={mode} onToggleMode={toggle}>
                      <Outlet />
                    </AppShell>
                  </SelectedProductProvider>
                </RequireAuth>
              }
            >
              <Route path="/home" element={<HomeRoute />} />
              <Route path="/activity" element={<ActivityRoute />} />
              <Route path="/new" element={<NewProductRoute />} />
              <Route path="/products/:productId/reading" element={<ReadingWebsiteRoute />} />
              <Route path="/products/:productId/plan" element={<PlanRoute />} />
              <Route path="/products/:productId/tracking" element={<TrackingRoute />} />
              <Route path="/opportunities" element={<OpportunitiesRoute />} />
              <Route path="/settings/product" element={<SettingsProductRoute />} />

              {/* From the previous flow. Unreachable from the new one and
                  kept only so nothing is lost while the plan and dashboard
                  are being designed. */}
              <Route path="/briefs" element={<BriefsRoute />} />
              <Route path="/plans/:planId" element={<ReviewPlanRoute />} />
              <Route path="/runs/:runId" element={<RunRoute />} />
              <Route path="/runs/:runId/results" element={<ResultsRoute />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
