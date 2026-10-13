# Frontend

React + Material UI, built with Vite. It talks to the FastAPI backend; there
is no mock data.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # type-check, then production build
```

Start the backend first. `vite.config.ts` proxies `/api` to
`http://localhost:8000`, so no CORS setup is needed in development.
`VITE_API_BASE` only matters when pointing at a deployed API.

## Screens

The flow is: landing → sign up → add a product → the site is read → plan →
search → results.

| Route | File | What it is |
|---|---|---|
| `/` | `routes/landing.tsx` | Public landing page |
| `/signup`, `/login` | `routes/signup.tsx`, `routes/login.tsx` | Accounts |
| `/forgot-password`, `/reset-password` | `routes/forgot-password.tsx`, `routes/reset-password.tsx` | Password reset |
| `/home` | `routes/home.tsx` | Where signing in lands you: the last search and its leads |
| `/new` | `routes/new-search.tsx` | Add a product: name and website |
| `/products/:productId/reading` | `routes/reading-website.tsx` | Progress while the website is read |
| `/products/:productId/plan` | `routes/plan.tsx` | The search plan, one card per platform, and the latest results |
| `/opportunities` | `routes/opportunities.tsx` | One search: progress while it runs, then the ranked results |
| `/products/:productId/tracking` | `routes/tracking.tsx` | What happened to the posts you replied to, for one product |
| `/activity` | `routes/activity.tsx` | The same totals across every product |
| `/settings/product` | `routes/settings-product.tsx` | Product websites |

`/briefs`, `/plans/:planId`, `/runs/:runId` and `/runs/:runId/results` belong
to an earlier flow. Nothing links to them any more.

## Rules that live in this code

1. **Every score can be opened.** `ScoreBreakdown` shows the parts and how
   they combine into the final number.
2. **The evidence quote is always the author's.** The backend checks the quote
   exists in the post before storing it.
3. **No blank pages.** Loading, empty and failed each have a real screen.
4. **The system never posts.** The reply drawer has a Copy button and nothing
   else.

## Notes

- `src/lib/types.ts` is written by hand. `npm run types` regenerates it from
  the backend's `/openapi.json` when the backend is running.
- The theme is in `src/styles/theme.ts`. Use MUI components and theme tokens.
  `tailwind.config.ts` and `src/components/ui/` are leftovers from an earlier
  plan and are not used.
