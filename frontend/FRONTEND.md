# Frontend — Milestone 7

Next.js 14 (App Router) + TypeScript + Tailwind. No shadcn/ui, despite
the original tech-stack sketch — see "Design decisions" below.

## What's real vs. not

Every page calls a real backend route from `backend/api/API.md` through
`services/api.ts`. Nothing in this app renders fabricated data:

| Page | Backed by | Status |
|---|---|---|
| Dashboard | `/api/planner/next-task`, `/api/tasks/`, derived client-side ratios | Live |
| Brain Dump | `/api/planner/brain-dump`, `/api/planner/goal` | Live |
| Projects | `/api/projects/*`, `/api/tasks/*` | Live |
| Calendar | `/api/calendar/*` | Live |
| AI Chat | `/api/planner/brain-dump`, `/replan`, `/next-task` | Live (see below) |
| Analytics | `/api/analytics/*` | Real calls, correctly render "not built yet" — routes are 501 until Milestone 8 |
| Settings | none (static docs + `NEXT_PUBLIC_API_URL`) | N/A |

## Design decisions

- **No shadcn/ui.** The original stack sketch listed it, but this app
  has ~10 component types total and a from-scratch token system
  (`tailwind.config.ts`) already fully specifies color/type/spacing —
  adding shadcn's copy-in component layer on top would mean maintaining
  two styling systems for no real benefit on a single-user app. Plain
  Tailwind + a handful of primitives in `components/ui/` does the job.
- **No fabricated "AI" metrics.** The original mockup in the planning
  doc showed a "Focus Score" and "Energy Prediction" — neither is
  backed by a real endpoint (energy prediction isn't modeled anywhere
  in the backend yet). Rather than invent a plausible-looking number,
  the dashboard's gauge shows **Due Today progress** — completed vs.
  total tasks due today, computed client-side from real `/api/tasks/`
  data. If Milestone 8 adds a real energy/focus model, this is where it
  plugs in.
- **AI Chat isn't a chatbot.** There's no `/api/chat` route — the AI
  layer is a pipeline of single-purpose agents
  (`backend/ai/AGENTS.md`), not a conversational model sitting behind
  the whole app. `/chat` is an honest front end for the three
  conversational entry points that do exist: every typed message runs
  through the brain-dump agent, and the two quick-action buttons call
  `/api/planner/replan` and `/api/planner/next-task` directly. It says
  what it's doing ("Working…"), never "thinking…".
- **Analytics calls the real 501s.** `analyticsApi.*` in `services/api.ts`
  hits the actual `/api/analytics/*` routes rather than being stubbed
  out client-side. Each panel catches `ApiError` with `status === 501`
  and renders an explicit "not built yet" state naming Milestone 8 —
  so the page needs zero code changes the moment that milestone lands.
- **App Router, not the `pages/` folder** sketched in Milestone 1's
  `ARCHITECTURE.md`. That folder predates the App Router becoming
  Next.js's default; `app/` replaces it. `styles/` was similarly folded
  into `app/globals.css` + Tailwind rather than kept as a separate tree.
- **SWR over a custom fetch-and-`useState` pattern.** Every list (tasks,
  projects, next-task, calendar events) needs revalidation after a
  mutation (complete a task, sync calendar) and periodic refresh (next
  task, calendar). SWR gives both in one hook without hand-rolled
  polling logic per page.
- **Typed by hand, not generated.** `services/types.ts` mirrors
  `backend/schemas/*.py` field-for-field, including which fields are
  absent from `*Create`/`*Update` (e.g. `priority_score` is
  server-only). The API surface is small and stable enough that a
  codegen step would be more overhead than the five interfaces it
  would produce.
- **Instrument-panel visual direction.** This is read at 7am and 11pm
  on one laptop, not a SaaS marketing dashboard — dark surface, hairline
  borders, tabular-mono numbers for anything that ticks over (hours,
  percentages, scores), a single radial gauge as the one signature
  element rather than decorative charts everywhere. Full token system
  in `tailwind.config.ts`.

## Verified

`npm install && npm run build` compiles clean: TypeScript strict mode,
zero ESLint errors, all 9 routes prerender. (Google Fonts — Space
Grotesk / Inter / IBM Plex Mono via `next/font/google` — need network
access at build time; verified separately with the fonts stubbed out
locally, then restored.)

## Next milestone

**Milestone 8 — Analytics and ML components**: implement
`backend/models/metrics.py` aggregation and turn `/api/analytics/*`
from `501` into real endpoints. `app/analytics/page.tsx` already calls
all four routes and needs no changes — its `AnalyticsPanel` component
will start rendering real JSON the moment the backend responds with
`200` instead of `501`. Once the response shapes are finalized there,
it's worth swapping the raw `JSON.stringify` fallback for real charts
(recharts is already a dependency, unused until then).
