# API Layer — Milestone 3

FastAPI app in `backend/app.py`. Interactive docs at `/docs` once running.

## Route table

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/health` | ✅ live | Liveness check |
| POST | `/api/projects/` | ✅ live | Create project |
| GET | `/api/projects/` | ✅ live | List, optional `?status_filter=` |
| GET | `/api/projects/{id}` | ✅ live | 404 if missing |
| PUT | `/api/projects/{id}` | ✅ live | Partial update |
| DELETE | `/api/projects/{id}` | ✅ live | Cascades to tasks |
| POST | `/api/tasks/` | ✅ live | Create task |
| GET | `/api/tasks/` | ✅ live | List, optional `?project_id=` `?status_filter=` |
| GET | `/api/tasks/{id}` | ✅ live | Includes nested `subtasks` |
| PUT | `/api/tasks/{id}` | ✅ live | Partial update |
| DELETE | `/api/tasks/{id}` | ✅ live | Cascades to subtasks/sessions/etc. |
| POST | `/api/tasks/{id}/complete` | ✅ live | Sets status + `completed_at` |
| POST | `/api/tasks/{id}/subtasks` | ✅ live | Create subtask under task |
| GET | `/api/tasks/{id}/subtasks` | ✅ live | List a task's subtasks |
| PUT | `/api/tasks/subtasks/{id}` | ✅ live | Update subtask |
| DELETE | `/api/tasks/subtasks/{id}` | ✅ live | Delete subtask |
| POST | `/api/planner/brain-dump` | 🔜 501 | Needs Milestone 4 (AI agents) |
| POST | `/api/planner/goal` | 🔜 501 | Needs Milestone 4 |
| GET | `/api/planner/next-task` | 🔜 501 | Needs Milestone 5 (scheduler) |
| POST | `/api/planner/replan` | 🔜 501 | Needs Milestone 5 |
| GET | `/api/analytics/*` (4 routes) | 🔜 501 | Needs Milestone 8 |
| GET/POST | `/api/calendar/*` (3 routes) | 🔜 501 | Needs Milestone 6 |
| GET/POST | `/api/todoist/*` (3 routes) | 🔜 501 | Needs Milestone 6 |

## Design decisions

- **`schemas/` is separate from `models/`.** ORM models describe what's
  stored; Pydantic schemas describe what's accepted/returned over HTTP.
  `TaskCreate` deliberately excludes `priority_score`,
  `confidence_score`, and `context_switch_cost` — those are AI/ML
  outputs, never client input.
- **`api/projects.py` wasn't in the original Milestone 1 sketch.**
  Projects are the parent entity for tasks and needed their own CRUD
  surface — adding the file was a natural, small extension of the
  planned structure rather than a scope change.
- **Everything not yet implemented returns `501`, not a fake 200.**
  Planner, Calendar, Todoist, and Analytics routes are registered (so
  the API surface and OpenAPI docs are stable and won't need a breaking
  change later) but each explicitly raises `HTTPException(501)` with a
  message naming the milestone that implements it. This was a
  deliberate choice over half-implementing e.g. a naive analytics
  endpoint now — cleaner to build it once, correctly, in Milestone 8.
- **Enum storage bug caught by testing, not by inspection.** SQLAlchemy's
  `Enum` column type stores an enum member's `.name` (e.g. `"ACTIVE"`)
  by default, not its `.value` (e.g. `"active"`). Since the Pydantic
  schemas validate against `.value` (lowercase, matching the API
  contract), this silently produced data that would fail to round-trip
  the moment something tried to read `status: "ACTIVE"` back as
  `ProjectStatus("ACTIVE")`. Fixed with a `sa_enum()` helper in
  `backend/models/enums.py` that passes `values_callable` so the DB
  stores `.value` everywhere. Caught by running the API end-to-end with
  `TestClient`, not by reading the code — worth remembering for future
  milestones.
- **`lifespan` context, not `@app.on_event`.** FastAPI's older
  `on_event("startup")` is deprecated; `app.py` uses the
  `@asynccontextmanager lifespan` pattern to call `init_db()` on boot.
- **CORS locked to `http://localhost:3000`.** This is a local, single-user
  app — no reason to open CORS wider until the frontend's actual dev
  port is confirmed in Milestone 7.

## Verified

Ran the full app through `TestClient` (with proper `lifespan` startup):
created a project, created a task under it, added a subtask, listed and
filtered tasks, fetched a task with nested subtasks, updated status,
completed a task, hit a 404 on a missing task, deleted a project and
confirmed the cascade removed its task, and confirmed all four
not-yet-implemented route groups return `501` with a clear message.
Also confirmed `app.openapi()` builds without errors and every planned
route appears in the schema.

## Next milestone

**Milestone 4 — Ollama integration and AI agents**: implement
`backend/ai/ollama_client.py` and the agent prompts, wire
`services/task_parser.py` + `services/planner_service.py`, and turn
`POST /api/planner/brain-dump` / `POST /api/planner/goal` from `501`
into real, working endpoints.
