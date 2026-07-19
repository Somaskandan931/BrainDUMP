# Architecture

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

   Google Calendar

(SQLite stores everything — data/tasks.db, data/history.db)
```

Everything runs on one machine. The only outbound network calls are the
optional Google Calendar sync; the LLM, database, and vector
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
│   │   ├── projects.py          CRUD for projects
│   │   ├── planner.py           brain-dump, goal, next-task, replan
│   │   ├── tasks.py             CRUD for tasks/subtasks
│   │   ├── analytics.py         weekly review, estimation error, streaks
│   │   └── calendar.py          Google Calendar sync endpoints
│   │
│   ├── schemas/                Pydantic request/response models
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
│   │   └── google_calendar.py
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
├── frontend/                     Next.js app — see frontend/FRONTEND.md
│   ├── app/  components/  hooks/  services/  lib/
│   └── package.json
│
├── data/        SQLite DBs (gitignored)
├── models/      Trained ML artifacts (.pkl, gitignored)
├── prompts/     Optional exported prompt versions for iteration/testing
├── logs/        Runtime logs (gitignored)
└── tests/       Pytest suite
```

### Why this layering

- **`api/` vs `services/`** — routes stay thin (parse request, call a
  service, return response). All real logic lives in `services/`, so it's
  testable without spinning up FastAPI and reusable by the scheduler jobs
  in `scheduler/`, which call services directly rather than hitting HTTP.
- **`ai/` vs `ml/`** — deliberately separate. `ai/` is the LLM agent layer
  (reasoning, parsing, natural language). `ml/` is classical
  regression/classification trained on the user's own logged data
  (predicted vs. actual hours). They solve different problems and evolve
  independently.
- **`integrations/` isolated from `services/`** — Google Calendar is
  the only component that talks to the outside world. Keeping
  them in one folder makes the "local-first, no data leaves the machine
  except X" guarantee easy to audit.
- **`scheduler/` (APScheduler jobs) vs `services/scheduler_service.py`** —
  the folder holds *when* things run (cron-like jobs); the service holds
  *how* slot-packing works. `morning.py`/`nightly.py` call into
  `scheduler_service.py` and `deadline_service.py`.

## 3. Data flow (planning pipeline)

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
Calendar Sync (integrations/)
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

`backend/ai/ollama_client.py` reads the model name from
`backend/config.py` so it can be swapped without touching agent code.

## 5. What's intentionally out of scope

No auth, no multi-user, no cloud database, no Docker Compose yet, no
team collaboration. Brain Dump is built for a single user's personal
execution — see the PRD's product philosophy for why.

## 6. Component documentation

Each subsystem below has its own doc with full design notes and
verified behavior:

- **API layer** — route table and design decisions: `backend/api/API.md`
- **AI agents** — Task Parser, Goal Breakdown, and the reasoning behind
  what's built vs. deferred: `backend/ai/AGENTS.md`
- **Database schema** — entity-relationship overview and table-by-table
  notes: `backend/models/SCHEMA.md`
- **Scheduler and planning engine** — estimator, priority scoring,
  slot-packing, and replanning: `backend/services/PLANNING.md`
- **Google Calendar integration** — setup steps and sync design:
  `backend/integrations/INTEGRATIONS.md`
- **Analytics and ML** — weekly review, estimation error, streaks, and
  the trained estimator: `backend/ANALYTICS.md`
- **Frontend** — pages, what's live, and design decisions:
  `frontend/FRONTEND.md`
