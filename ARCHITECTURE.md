# Architecture — Milestone 1

## 1. System overview

```
                     ┌────────────────────────┐
                     │      Next.js Dashboard │
                     └────────────┬───────────┘
                                  │
                            REST / WebSocket
                                  │
                     ┌────────────▼────────────┐
                     │      FastAPI Server      │
                     └────────────┬────────────┘
                                  │
          ┌──────────┬───────────┼───────────┬───────────┐
          │          │           │           │           │
          ▼          ▼           ▼           ▼           ▼
     Planner AI  Scheduler   Task Engine   Analytics    Memory
          │
          ▼
     Ollama (local LLM: qwen3:8b / llama3.1:8b / gemma3:4b)

          │
          ▼

   Google Calendar          Todoist

(SQLite stores everything — data/tasks.db, data/history.db)
```

Everything runs on one machine. The only outbound network calls are the
optional Google Calendar and Todoist syncs; the LLM, database, and vector
search are all local.

## 2. Folder structure and rationale

```
ai_os/
├── README.md               High-level orientation + quickstart
├── ARCHITECTURE.md          This file
├── .gitignore
│
├── backend/
│   ├── app.py                FastAPI entrypoint — registers routers only
│   ├── config.py              Central settings (paths, model name, flags)
│   ├── database.py            SQLAlchemy engine/session/Base
│   ├── requirements.txt
│   │
│   ├── api/                   HTTP layer only — thin, delegates to services/
│   │   ├── projects.py          CRUD for projects (added M3 — see below)
│   │   ├── planner.py           brain-dump, goal, next-task, replan
│   │   ├── tasks.py             CRUD for tasks/subtasks
│   │   ├── analytics.py         weekly review, estimation error, streaks
│   │   ├── calendar.py          Google Calendar sync endpoints
│   │   └── todoist.py           Todoist sync endpoints
│   │
│   ├── schemas/                Pydantic request/response models (added M3)
│   │   ├── project.py           ProjectCreate/Update/Read
│   │   └── task.py              Task*/Subtask* schemas
│   │
│   ├── services/               Business logic — orchestrates ai/ + ml/
│   │   ├── planner_service.py   Runs the full brain-dump -> schedule pipeline
│   │   ├── scheduler_service.py Packs tasks into free calendar slots
│   │   ├── deadline_service.py  Dynamic replanning when work slips
│   │   ├── task_parser.py       NL -> structured task/project extraction
│   │   └── notification_service.py
│   │
│   ├── ai/                     LLM layer (Ollama-backed agents)
│   │   ├── ollama_client.py     Single wrapper all agents call through
│   │   ├── prompts.py           One prompt template per agent
│   │   ├── embeddings.py        sentence-transformers + FAISS semantic search
│   │   └── memory.py            Working context (e.g. "Question 3" resolution)
│   │
│   ├── ml/                     Classical ML layer (separate from the LLM)
│   │   ├── estimator.py         Predicts task duration from history
│   │   ├── priority_model.py    Composite priority scoring
│   │   └── trainer.py           Retraining pipeline, run on a schedule
│   │
│   ├── integrations/            External API wrappers, nothing else
│   │   ├── google_calendar.py
│   │   └── todoist.py
│   │
│   ├── models/                  SQLAlchemy ORM models
│   │   ├── project.py
│   │   ├── task.py               + Subtask
│   │   └── session.py            WorkSession (timer/focus sessions)
│   │
│   ├── scheduler/                APScheduler background jobs
│   │   ├── morning.py            7 AM: generate today's plan
│   │   └── nightly.py            Reschedule + summarize + Sunday review
│   │
│   └── utils/                    Shared helpers (logging, date math, etc.)
│
├── frontend/                     Next.js app (Milestone 7 — done)
│   ├── app/  components/  hooks/  services/  lib/
│   └── package.json              See frontend/FRONTEND.md
│
├── data/        SQLite DBs (gitignored)
├── models/      Trained ML artifacts (.pkl, gitignored)
├── prompts/     Optional exported prompt versions for iteration/testing
├── logs/        Runtime logs (gitignored)
└── tests/       Pytest suite (Milestone 9)
```

### Why this layering

- **`api/` vs `services/`** — routes stay thin (parse request, call a
  service, return response). All real logic lives in `services/`, so it's
  testable without spinning up FastAPI and reusable by the scheduler jobs
  in `scheduler/`, which call services directly rather than hitting HTTP.
- **`ai/` vs `ml/`** — deliberately separate. `ai/` is the LLM agent layer
  (reasoning, parsing, natural language). `ml/` is classical
  regression/classification trained on the user's own logged data
  (predicted vs. actual hours). They solve different problems and will
  likely evolve independently.
- **`integrations/` isolated from `services/`** — Google Calendar and
  Todoist are the only components that talk to the outside world. Keeping
  them in one folder makes the "local-first, no data leaves the machine
  except X" guarantee easy to audit.
- **`scheduler/` (APScheduler jobs) vs `services/scheduler_service.py`** —
  the folder holds *when* things run (cron-like jobs); the service holds
  *how* slot-packing works. `morning.py`/`nightly.py` call into
  `scheduler_service.py` and `deadline_service.py`.

## 3. Data flow (planning pipeline, implemented in Milestone 5)

```
Brain Dump
   │
   ▼
Intent Extraction (ai/)
   │
   ▼
Project Detection (services/task_parser.py)
   │
   ▼
Task Breakdown (ai/)
   │
   ▼
Time Estimation (ml/estimator.py)
   │
   ▼
Dependency Detection
   │
   ▼
Priority Calculation (ml/priority_model.py)
   │
   ▼
Schedule Optimization (services/scheduler_service.py)
   │
   ▼
Calendar Sync + Todoist Sync (integrations/)
   │
   ▼
Dashboard Update
```

## 4. Local model choice

Ollama is assumed already installed. Recommended pull, sized to RAM:

```powershell
ollama pull qwen3:8b       # 16GB RAM — best balance
ollama pull llama3.1:8b    # alternative
ollama pull gemma3:4b      # lower RAM usage
```

`backend/ai/ollama_client.py` (Milestone 4) reads the model name from
`backend/config.py` so it can be swapped without touching agent code.

## 5. What's intentionally deferred

No auth, no multi-user, no cloud database, no Docker Compose yet (that's
Milestone 9), no actual endpoint logic, no ORM field definitions. This
milestone only fixes the *shape* of the system so every later milestone
has an unambiguous place to land.

## Milestone history
see `backend/models/SCHEMA.md`.

~~**Milestone 3 — FastAPI backend with clean APIs**~~ ✅ done — full
CRUD for Project/Task/Subtask, all other routes registered and honestly
stubbed at `501`. See `backend/api/API.md` for the full route table and
design notes.

~~**Milestone 4 — Ollama integration and AI agents**~~ ✅ done —
`POST /api/planner/brain-dump` and `POST /api/planner/goal` are real.
See `backend/ai/AGENTS.md` for the agent design notes, including why
Deadline Generator was folded into the Task Parser prompt instead of
being a separate chained call, and why `ai/memory.py` / `ai/embeddings.py`
stay stubs for now.

~~**Milestone 5 — Scheduler and planning engine**~~ ✅ done —
`backend/ml/estimator.py` and `backend/ml/priority_model.py` are real
(statistical estimator, hand-tuned weighted-sum priority score),
`services/scheduler_service.py` and `services/deadline_service.py` are
wired through `services/planner_service.py`, and `GET /api/planner/next-task`
/ `POST /api/planner/replan` are live. `priority_score` and
`context_switch_cost` on `Task` are now populated for real, and the
`morning`/`nightly` APScheduler jobs run the scheduler and replan
pipeline on a cron. See `backend/services/PLANNING.md` for the full
design notes.

~~**Milestone 6 — Google Calendar and Todoist integrations**~~ ✅ done —
`backend/integrations/google_calendar.py` (OAuth flow, `list_events()`,
`get_free_busy()`, `create_event()`/`update_event()`/`delete_event()`)
and `backend/integrations/todoist.py` (`pull_tasks()`/`push_task()`,
priority mapping) are real, backed by
`services/calendar_sync_service.py` and `services/todoist_sync_service.py`.
`POST/GET /api/calendar/*` and `POST/GET /api/todoist/*` are live —
`generate_free_slots()` didn't need to change at all, since it already
read busy time from `CalendarEvent` regardless of source; this milestone
just populates that table with real Google events (`source=GOOGLE`) and
adds `Task.todoist_id` for two-way reconciliation. Both integrations are
opt-in and fail soft independently. See
`backend/integrations/INTEGRATIONS.md` for setup steps and design notes.

~~**Milestone 8 — Analytics and ML components**~~ ✅ done —
`backend/services/analytics_service.py` computes all four
`/api/analytics/*` responses live from `ProductivityMetric`/`Task`/
`Prediction`/`WorkSession` (`weekly-review`, `estimation-error`,
`streaks`, `productivity-hours`); `weekly-review` closes with a one-
sentence AI recommendation from a new Reflection Agent, with a rule-
based fallback if Ollama is offline. `backend/ml/trainer.py` adds a
`RandomForestRegressor` as a second tier in `ml/estimator.py`, trained
weekly (Sundays) from the nightly job once 20+ resolved `Prediction`
rows exist. `ml/priority_model.py` deliberately stays the Milestone 5
hand-tuned weighted sum — see `backend/ANALYTICS.md` for why a learned
version isn't a real fit without a schema change. `frontend/app/analytics/page.tsx`
needed zero changes — it was already calling the real routes and
rendering whatever came back. See `backend/ANALYTICS.md` for full design
notes.

## Next milestone

**Milestone 7 — Next.js frontend**: done — see `frontend/FRONTEND.md`
for what was built and the design decisions behind it.

**Milestone 9 — Testing and Docker**: turn the manual check scripts in
`tests/` (`manual_milestone6_check.py`, `manual_milestone8_check.py`)
into a real `pytest` suite — with coverage added for Milestones 1-5 and
7, which never got a dedicated script — and add a `docker-compose.yml`
that brings up the backend, frontend, and Ollama together for
one-command local setup.
