# API Layer

FastAPI app in `backend/app.py`. Interactive docs at `/docs` once running.

## Route table

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/health` | Live | Liveness check |
| POST | `/api/projects/` | Live | Create project |
| GET | `/api/projects/` | Live | List, optional `?status_filter=` |
| GET | `/api/projects/{id}` | Live | 404 if missing |
| PUT | `/api/projects/{id}` | Live | Partial update |
| DELETE | `/api/projects/{id}` | Live | Cascades to tasks |
| POST | `/api/tasks/` | Live | Create task |
| GET | `/api/tasks/` | Live | List, optional `?project_id=` `?status_filter=` |
| GET | `/api/tasks/{id}` | Live | Includes nested `subtasks` |
| PUT | `/api/tasks/{id}` | Live | Partial update |
| DELETE | `/api/tasks/{id}` | Live | Cascades to subtasks/sessions/etc. |
| POST | `/api/tasks/{id}/complete` | Live | Sets status + `completed_at` |
| POST | `/api/tasks/{id}/subtasks` | Live | Create subtask under task |
| GET | `/api/tasks/{id}/subtasks` | Live | List a task's subtasks |
| PUT | `/api/tasks/subtasks/{id}` | Live | Update subtask |
| DELETE | `/api/tasks/subtasks/{id}` | Live | Delete subtask |
| POST | `/api/planner/brain-dump` | Live | Natural-language capture -> structured tasks |
| POST | `/api/planner/goal` | Live | Goal -> Project + task roadmap |
| GET | `/api/planner/next-task` | Live | `{"task": null}` if nothing active |
| POST | `/api/planner/replan` | Live | Dynamic rescheduling |
| GET | `/api/analytics/weekly-review` | Live | Stats computed live, AI recommendation with rule-based fallback |
| GET | `/api/analytics/estimation-error` | Live | Grouped by project/importance category |
| GET | `/api/analytics/streaks` | Live | Completion streaks |
| GET | `/api/analytics/productivity-hours` | Live | Buckets `WorkSession` by hour of day |
| GET | `/api/calendar/events` | Live | Local cache, optional `?source=` |
| POST | `/api/calendar/sync` | Live | 424 if `credentials.json` missing |
| POST | `/api/calendar/create-session` | Live | Ad hoc "start now" session |

## Design decisions

- **`schemas/` is separate from `models/`.** ORM models describe what's
  stored; Pydantic schemas describe what's accepted/returned over HTTP.
  `TaskCreate` deliberately excludes `priority_score`,
  `confidence_score`, and `context_switch_cost` — those are AI/ML
  outputs, never client input.
- **`api/projects.py` wasn't in the original architecture sketch.**
  Projects are the parent entity for tasks and needed their own CRUD
  surface — adding the file was a natural, small extension of the
  planned structure rather than a scope change.
- **Anything not yet implemented returns `501`, not a fake 200, while
  it's being built.** Routes are registered up front (so the API
  surface and OpenAPI docs are stable and don't need a breaking change
  later) but explicitly raise `HTTPException(501)` naming what still
  needs to land, rather than half-implementing something like a naive
  analytics endpoint early — cleaner to build each piece once,
  correctly. Planner and Calendar routes went through that path and are
  now live; Analytics followed the same pattern and is now live too —
  see `backend/services/analytics_service.py` and `ANALYTICS.md`.
- **Enum storage bug caught by testing, not by inspection.** SQLAlchemy's
  `Enum` column type stores an enum member's `.name` (e.g. `"ACTIVE"`)
  by default, not its `.value` (e.g. `"active"`). Since the Pydantic
  schemas validate against `.value` (lowercase, matching the API
  contract), this silently produced data that would fail to round-trip
  the moment something tried to read `status: "ACTIVE"` back as
  `ProjectStatus("ACTIVE")`. Fixed with a `sa_enum()` helper in
  `backend/models/enums.py` that passes `values_callable` so the DB
  stores `.value` everywhere. Caught by running the API end-to-end with
  `TestClient`, not by reading the code.
- **`lifespan` context, not `@app.on_event`.** FastAPI's older
  `on_event("startup")` is deprecated; `app.py` uses the
  `@asynccontextmanager lifespan` pattern to call `init_db()` on boot.
- **CORS locked to `http://localhost:3000`.** This is a local, single-user
  app — no reason to open CORS wider than the frontend's actual dev port.

## Verified

Ran the full app through `TestClient` (with proper `lifespan` startup):
created a project, created a task under it, added a subtask, listed and
filtered tasks, fetched a task with nested subtasks, updated status,
completed a task, hit a 404 on a missing task, deleted a project and
confirmed the cascade removed its task. Also confirmed `app.openapi()`
builds without errors and every route appears in the schema.
