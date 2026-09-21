# Reorganization notes (this pass)

## Done

1. **Merged `backend-usage-limit-feature/`** (the unmerged per-user AI usage-cap
   branch) into `backend/`: `models/usage.py`, `services/usage_service.py`,
   migration `0007_add_usage_records.py`, and the `db=db` wiring in
   `ollama_client.py`, `planner_service.py`, `task_parser.py`,
   `analytics_service.py`, `ai_coach_service.py`, `scheduler/morning.py`,
   `api/planner.py` (adds HTTP 429 when a user hits `AI_DAILY_CALL_LIMIT`,
   default 50/day). The old `backend-usage-limit-feature/` folder is deleted.

2. **`backend/` restructured into `backend/app/`**, domain-organized, per the
   "Stage 1" plan:
   - `app.py` -> `app/main.py`
   - `config.py` -> `app/core/config.py`
   - `database.py` -> `app/db/database.py`
   - `migrate.py` -> `app/db/migrate.py`
   - `auth/`, `models/`, `schemas/`, `ai/`, `ml/`, `integrations/`, `utils/`
     -> `app/auth/`, `app/models/`, etc. (unchanged internally)
   - `api/` -> `app/api/v1/` (versioned; `app/main.py` imports from here)
   - `scheduler/morning.py`, `scheduler/nightly.py` (APScheduler cron jobs)
     -> `app/jobs/tasks/morning_plan.py`, `app/jobs/tasks/nightly_replan.py`
   - `services/` split by domain:
     - `app/services/planning/` — planner_service, schedule_service,
       scheduler_service, deadline_service, workload_service, task_parser
     - `app/services/ai/` — ai_coach_service, explanation_service, usage_service
     - `app/services/productivity/` — analytics_service,
       execution_score_service, notification_service
     - `app/services/integrations/` — calendar_sync_service,
       todoist_sync_service, integration_credentials_service
     - `app/services/workspace/` — user_settings_service, demo_service
   - `backend/migrations/` (Alembic) stays at the top of `backend/`, not
     under `app/` — it's schema history, not application code.
   - **~85 files' imports rewritten** accordingly, including splitting
     several combined imports that crossed domain boundaries (e.g.
     `scheduler/morning.py` pulled from three different service domains
     in one `from backend.services import a, b, c`).
   - File names were **not** changed (e.g. still `calendar_sync_service.py`,
     not `calendar_service.py`) to keep the diff mechanical and low-risk —
     only *where* files live changed, not what they're called.

3. **Config made Postgres-ready without breaking SQLite dev**:
   `config.py` now reads `DATABASE_URL` from the environment (falling back
   to the existing `sqlite:///data/tasks.db`), and `database.py` only
   applies SQLite's `check_same_thread` flag when SQLite is actually
   active. `psycopg[binary]` added to `requirements.txt`. This is the P0
   change from the architecture review — deploying against Postgres is now
   just setting one env var, no code change.

4. **Stray docs recovered**: `AGENTS.md`, `API.md`, `SCHEMA.md`,
   `INTEGRATIONS.md`, `PLANNING.md`, `ANALYTICS.md` (previously sitting
   inside code folders, easy to lose) moved to `docs/api/` and
   `docs/architecture/`.

5. **Verified, not just compiled**: every `.py` file passes `py_compile`,
   and `backend.app.main:app` (the real FastAPI app), the full service
   layer, and `alembic` migrate-to-head (`0007`) were all actually
   imported/run in a clean environment — not just syntax-checked.

## Not done in this pass (deliberately, to keep this change reviewable)

- `deploy-kit/` still duplicates the root `render.yaml` / `DEPLOY.md` /
  `.env.example`. Worth folding into one `infrastructure/` + `deploy/`
  pair, but touches deployment configs I didn't want to guess at blindly.
- `tests/` is still flat, not yet split into `unit/`, `integration/`,
  `security/`.
- `README.md` still says "local-first" / shows an Ollama badge even
  though the backend now calls OpenRouter — worth a follow-up edit.
- `frontend/services/api.ts` + `types.ts` not yet moved to `frontend/lib/api/`.
- No repository-pattern layer, Redis, background worker (Celery/ARQ), or
  Workspace model were added — those are real architectural changes, not
  file moves, and shouldn't be done as part of a reorg pass.

## How to verify locally

```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt
cd ..
BRAINDUMP_DATA_DIR=/tmp/bd_data JWT_SECRET_KEY=dev python -c "from backend.app.main import app; print(app.title)"
pytest tests -q
```
