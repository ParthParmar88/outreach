import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,

    // Deliberately not `open: true`.
    //
    // That opens a browser tab every time the dev server starts - and Vite
    // restarts itself whenever this file changes, so editing the config, or
    // pulling a branch that touched it, silently spawns another tab. From
    // the keyboard it looks like whatever you last clicked opened one,
    // which is a confusing thing to chase through the application code
    // where no `target="_blank"` and no `window.open` exist.
    //
    // Open http://localhost:5173 yourself once and keep the tab.
    open: false,

    // Serve beyond localhost, so a tunnel can reach the dev server.
    host: true,

    // Vite 6 rejects any request whose Host header it does not recognise,
    // which is every request arriving through a tunnel: the browser sends
    // the tunnel's hostname, not localhost, and the reply is "Blocked
    // request. This host is not allowed." rather than anything hinting that
    // hosts are configurable.
    //
    // Named domains rather than `true`. `true` accepts any Host at all,
    // which re-opens the DNS-rebinding hole this check exists to close.
    // ngrok hands out `.ngrok-free.dev` now, not the `.ngrok-free.app` the
    // docs still show, so both are here. A leading dot matches subdomains,
    // which is what makes this survive the free tier handing out a fresh
    // name on every restart.
    allowedHosts: [
      ".ngrok-free.dev",
      ".ngrok-free.app",
      ".ngrok.app",
      ".ngrok.io",
    ],

    proxy: {
      // So the browser talks to the FastAPI service without CORS in dev.
      //
      // 127.0.0.1 and not "localhost". On Windows, Node resolves localhost
      // to ::1 first and does not fall back, while uvicorn binds 127.0.0.1
      // only - so every /api call answers 502 and the app looks like the
      // backend is down when it is running perfectly well.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
