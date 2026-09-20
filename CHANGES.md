# Changes

Relative to `brain-dump-project.zip`: **10 added (including this file and `START-HERE.md`), 61 modified, 4 deleted.**
Backend suite: 158 tests passing. Frontend: `tsc --noEmit` and `next lint` clean.
See `AUTH_REFACTOR_STATUS.md` for the bugs found and the known follow-ups.

## Deleted (dead code)
The Todoist sync layer. It referenced `Task.todoist_id`, which migration `0002` dropped on purpose, so
every call would have raised `AttributeError`. Also removed its router registration and config.

- `backend/api/todoist.py`
- `backend/integrations/todoist.py`
- `backend/schemas/todoist.py`
- `backend/services/todoist_sync_service.py`

> If you apply the changes-only zip over an existing tree, **delete these four files by hand** — a zip
> can't express deletions.

## Added

- `START-HERE.md` — how to apply, run, configure and deploy this package
- `backend/auth/rate_limit.py` — in-memory sliding-window limiter for login/register/Google sign-in
- `backend/migrations/versions/0005_calendar_event_id_unique_per_user.py` — `google_event_id` unique per user instead of globally
- `backend/services/integration_credentials_service.py` — per-user Google credential storage, encrypted at rest
- `frontend/components/settings/GoogleCalendarCard.tsx` — Settings card: connect / disconnect Google Calendar
- `tests/test_auth.py` — auth, tokens, rate limiting, Google-link policy, every-route-protected guard
- `tests/test_fresh_install.py` — empty data dir -> app boots -> first user registers and works
- `tests/test_integrations.py` — credential storage/encryption, OAuth endpoints, per-user calendar sync
- `tests/test_tenant_isolation.py` — two-user isolation across sessions, API, services and background jobs

## Modified

### Tenant scoping: `user_id=owner_id(db)` on every insert / unused imports
- `backend/ai/episodic_memory.py`
- `backend/ai/long_term_memory.py`
- `backend/ai/semantic_memory.py`
- `backend/api/analytics.py`
- `backend/api/chat.py`
- `backend/api/demo.py`
- `backend/api/memory.py`
- `backend/api/notifications.py`
- `backend/api/planner.py`
- `backend/api/schedule.py`
- `backend/api/settings.py`
- `backend/ml/estimator.py`
- `backend/services/demo_service.py`
- `backend/services/planner_service.py`
- `backend/services/schedule_service.py`
- `backend/services/scheduler_service.py`
- `backend/services/task_parser.py`
- `backend/services/user_settings_service.py`

### Auth hardening and tenant filter
- `backend/api/auth.py`
- `backend/api/tasks.py`
- `backend/auth/security.py`
- `backend/config.py`
- `backend/database.py`
- `backend/models/user.py`
- `backend/requirements.txt`

### Per-user Google Calendar
- `backend/api/API.md`
- `backend/api/calendar.py`
- `backend/integrations/INTEGRATIONS.md`
- `backend/integrations/google_calendar.py`
- `backend/models/calendar_event.py`
- `backend/schemas/calendar.py`
- `backend/services/calendar_sync_service.py`

### Background jobs (one pass per user)
- `backend/scheduler/morning.py`
- `backend/scheduler/nightly.py`

### App wiring (Todoist router removed)
- `backend/app.py`

### Migrations
- `backend/migrations/versions/0003_add_users_and_scope_data.py`
- `backend/migrations/versions/0004_scope_settings_and_memory_to_user.py`

### Deploy kit (rebuilt from the current backend; new env vars; proxy headers)
- `deploy-kit/.env.example`
- `deploy-kit/DEPLOY-FREE.md`
- `deploy-kit/DEPLOY.md`
- `deploy-kit/backend/Dockerfile`
- `deploy-kit/backend/app.py`
- `deploy-kit/backend/config.py`
- `deploy-kit/backend/requirements.txt`
- `deploy-kit/render.free.yaml`
- `deploy-kit/render.yaml`

### Frontend
- `frontend/app/login/page.tsx`
- `frontend/app/register/page.tsx`
- `frontend/app/settings/page.tsx`
- `frontend/components/auth/GoogleButton.tsx`
- `frontend/components/layout/AppShell.tsx`
- `frontend/components/layout/RouteGuard.tsx`
- `frontend/services/api.ts`
- `frontend/services/types.ts`

### Tests (per-user fixtures, migration tests)
- `tests/conftest.py`
- `tests/helpers.py`
- `tests/test_calibration.py`
- `tests/test_demo_workspace.py`
- `tests/test_explanations.py`
- `tests/test_migrations.py`

### Docs
- `AUTH_REFACTOR_STATUS.md`
