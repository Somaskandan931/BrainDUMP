# Production readiness — status vs. the SaaS review

Tracks this project against the priority table from the "single-user →
multi-tenant SaaS" architecture review. P0 items are security/correctness;
P1 is what breaks under real multi-instance load; P2 is future product work.

## P0 — done before this pass

- **PostgreSQL-ready persistence** — `DATABASE_URL` env-driven
  (`core/config.py`); SQLite stays the zero-setup local-dev default, but
  nothing above the engine cares which is active.
- **Tenant isolation** — every user-owned table is scoped by `user_id`;
  `api/deps.get_scoped_db` stamps `session.info["user_id"]` and
  `db/database.py`'s `do_orm_execute` listener enforces the filter at the
  session level (not just "remember to add `.filter(user_id=...)`
  everywhere"). Covered by `tests/security/test_tenant_isolation.py`.
- **Production secrets/config** — `JWT_SECRET_KEY`,
  `INTEGRATION_ENCRYPTION_KEY`, OAuth client secrets, etc. all come from
  env vars with dev-only insecure defaults that are clearly labeled as such.

## P0 — done in this pass

- **Email verification** — `users.is_verified` (migration `0008b`), SMTP/local-dev email delivery in `services/email_service.py`, and `/api/auth/verify-email/confirm`. New password registrations are unverified by default; login, refresh, and tenant-scoped API access are blocked until verification. OAuth accounts remain verified because the provider has authenticated the email address.
- **Password reset** — `/api/auth/password-reset/{request,confirm}` with an identical generic request response whether or not an address is registered. Reset tokens are short-lived purpose-scoped JWTs and are bound to the password hash that existed when they were issued, so changing the password invalidates replay of the same token. All refresh sessions are revoked after a successful reset.
- **Frontend auth flow** — `/forgot-password`, `/reset-password`, and `/verify-email` are wired to the real endpoints; verification/reset routes are public and new registrations land on a pending-verification screen.
- **Auth session model** — access JWTs are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30 minutes) and refresh tokens are random, hashed server-side, rotated, reuse-detected, and held only in an HttpOnly cookie. `/logout` revokes the current refresh session.

## Remaining auth hardening

- Verification links are idempotent rather than permanently storing a consumed-token record; a redeemed verification JWT can be presented again while it remains valid, but it has no further effect because the account is already verified. Password-reset tokens are invalidated by the password-version binding described above.

## P1 — done in this pass

- **Redis-backed rate limiter** — `auth/rate_limit.py`'s
  `RedisSlidingWindowLimiter` shares state across every API instance via
  one Redis sorted set per key, behind a `get_limiter()` factory that
  falls back to the original in-memory `SlidingWindowLimiter` when
  `config.REDIS_URL` is unset *or* Redis is unreachable — a Redis outage
  degrades rate limiting to per-process, it doesn't take auth down. All 7
  limiter call sites in `api/v1/auth.py` swapped over. 10 new tests
  against `fakeredis` (`tests/security/test_rate_limit_redis.py`).
- **Stop the scheduler from double-firing across instances** —
  `jobs/distributed_lock.py`'s `job_lock()` wraps the morning/nightly
  cron entry points (`main.py`'s `_locked_morning_job`/
  `_locked_nightly_job`) in a Redis `SET NX EX` lock scoped to the job
  name + current hour: whichever instance's trigger fires first claims
  the run, every other instance skips and logs it. Same "no Redis
  configured or Redis down => proceed anyway" fallback as the rate
  limiter, so this is a no-op change for a single-instance deployment.
  APScheduler itself still runs inside every API process — this doesn't
  move job execution to a separate worker, it just stops the *duplicate
  execution* symptom. A real worker split (Celery/ARQ/RQ) is still the
  "do this properly" version if job volume grows past what a lock-guarded
  cron fire can handle. 7 new tests (`tests/unit/test_job_lock.py`).
- Both features share one cached Redis connection per process
  (`core/redis_client.py`) rather than opening two.
- Full suite (this section's items): 187/187 green.

## P1 — done in this pass

- **Structured logs + error monitoring** — `core/logging_config.py`
  replaces the default unconfigured logger with one JSON-line-per-record
  formatter on stdout (Render already collects stdout; JSON is the
  lowest-common-denominator format for shipping it to a log sink).
  `core/request_logging.py`'s middleware logs one line per request
  (method, path, status, duration_ms, user_id, client_ip) and stamps a
  request_id — reused from an inbound `X-Request-ID` header if present,
  otherwise generated — onto every log line emitted while handling that
  request via a ContextVar, and echoes it back in the response header for
  end-to-end tracing across proxies. `core/sentry.py`'s `init_sentry()`
  turns on Sentry exception capture + Sentry's own logging integration
  (so existing `logger.exception(...)` calls, e.g. in the morning/nightly
  jobs, reach Sentry with no extra call needed) when `SENTRY_DSN` is set;
  a no-op otherwise, and tolerant of Sentry itself failing to initialize
  (monitoring going down isn't a reason to take the app down with it).
  `send_default_pii=False` — request bodies (passwords, OAuth codes)
  never get sent to Sentry.
  13 new tests (`tests/unit/test_observability.py`).

## P1 — done in this pass

- **Audit log + the "why did BrainDUMP move this?" trail** —
  `models/activity.py` (`activity_log`, migration `0009`) is an append-only,
  per-user record of what happened: who (`user_id`), what (`action`, e.g.
  `task.completed`), what it acted on (`entity_type`/`entity_id`), who caused
  it (`actor`: `user`, `system` for scheduled jobs, `ai` for brain-dump/goal
  flows), and a sanitized JSON `details`. Written through
  `services/workspace/activity_service.py`'s `log_activity()`, which stages the
  row on the caller's session **without committing**, so it persists or rolls
  back atomically with the change it describes, and never raises (auditing
  can't break the audited operation). Secret-looking keys are dropped at any
  depth, sizes are capped, and raw user text (brain-dump / goal text, task
  descriptions) is deliberately not copied in — ids, counts, field names and
  old/new values of small structured fields only.
  - **What's recorded:** task create / edit (old→new for title, status,
    importance, deadline, estimates, project; field *names only* for free
    text; a no-op PUT records nothing) / complete / skip / archive; project
    create / update / complete / delete (the delete row keeps the name and task
    count, since `entity_id` is intentionally not a foreign key); brain dump
    and goal plans (one summary row plus one `task.created` per task, with
    `source`); replan and — the "why" — every deadline the planner pushes out
    (`task.deadline_changed`: reason, importance, whether it was already
    overdue, days pushed, exact before/after); start-day; Google Calendar
    connect/disconnect; registration, email verification, password reset
    (never the password or token).
  - **Read API:** `GET /api/activity/` (newest first, cursor-paged, filter by
    entity/action) and `GET /api/tasks/{id}/history`. Read-only — there is no
    endpoint that writes or edits a row, so a client can't forge its own
    history. Tenant-isolated twice over: `ActivityLog` is registered with the
    session-level tenant filter *and* the query filters on the scoped user
    explicitly.
  - **Retention:** `ACTIVITY_LOG_RETENTION_DAYS` (default 180; 0 = keep
    everything); the nightly job prunes each user's old rows in its own
    transaction, so a purge failure can't undo a replan.
  - **Frontend:** typed client (`activityApi`, `tasksApi.history`) plus the
    task-history UI in `components/tasks/TaskHistory.tsx`; deadline changes
    render the recorded from/to values and actor.
  - **Known limits:** a replan repacks the whole schedule, and per-task rows
    for every repacked task every night would be N rows/user/night, so only
    *deadline* moves are per-task; the repack itself is one
    `schedule.replanned` row (written only when something changed) listing the
    demoted/at-risk task ids. A chat-triggered replan (`ai_coach_service`) is
    attributed to `user`, since the user asked for it.
  - 63 new tests (`tests/unit/test_activity_log.py`,
    `tests/integration/test_activity_api.py`); full suite is 274/274 green.

## P0 — found and fixed in this pass

- **Duplicate Alembic revision head** — `migrations/versions/0008_add_user_is_verified.py`
  and `0008_add_refresh_tokens.py` both claimed revision id `0008` with
  `down_revision = "0007"`; the correctly-renamed `0008b_add_user_is_verified.py`
  (which chains onto `0008`, then `0009` onto `0008b`) was the one actually meant
  to ship. The stray duplicate broke schema stamping for nearly every test that
  boots the app — deleting it took the suite from 115 passed / 145 errors to
  264 passed / 10 failed in one change. The four dead Todoist files (already
  unregistered, see "Removed (dead code)" above) were also still present in the
  tree and have now actually been deleted, not just documented as removed.
- **`deadline_service.demote_task` crashed on any at-risk task** —
  `task.deadline` comes back from SQLite timezone-naive; comparing it directly
  against `datetime.now(timezone.utc)` raised `TypeError`. This broke the
  nightly replan job for every task with a deadline. Fixed using the existing
  `utils/timeutil.ensure_utc()` helper (the same normalization
  `explanation_service.py` and `scheduler_service.py` already use elsewhere) —
  both for the comparison and for the `task.deadline_changed` audit row's
  `from` timestamp.
- **`api/v1/tasks.py`'s deadline diff omitted the UTC offset** on the "from"
  side of `task.updated` audit rows (SQLite hands the pre-update value back
  naive; the "to" side is already tz-aware since it came straight off the
  request). Same `ensure_utc()` fix.
- **`GET/DELETE /api/calendar/google` double-logged `calendar.disconnected`**
  on a second, no-op disconnect call, and never recorded `calendar.connected`'s
  `details`. Disconnect now only logs when there was something to disconnect
  (and records how many cached events it dropped); connect now records
  `{"provider": "google"}` to match what the rest of the audit trail does for
  every other integration action.
- **`schemas/activity.py`'s `ActivityEntryOut.created_at` wasn't going through
  `utc_iso()`** like every other `*Read` schema with a datetime field, so
  activity-log timestamps came back without a UTC offset. Added the same
  `@field_serializer` the rest of the API already uses.

Full suite after this pass: **274/274 green** (up from 115/260 before the
migration fix).

## P0 — still open

No original P0 auth item remains open from the 22-point SaaS plan. The remaining P0 work is operational hardening around production deployment: ensure strong non-dev secrets are supplied, use HTTPS, and point production instances at PostgreSQL/Redis rather than the SQLite/in-memory development fallbacks.

## P1 — still open

- **AI usage limits** — already done (`services/ai/usage_service.py`,
  `config.AI_DAILY_CALL_LIMIT`), not open.
- **Demo mode** — `api/v1/demo.py` + `services/workspace/demo_service.py`
  already seed/reset a workspace for the current authenticated user; this
  covers the "let a recruiter click around" need without a separate
  public demo account. Not open.
- **Metrics** — done, not open. `ENABLE_METRICS` (default on) wires
  `prometheus_fastapi_instrumentator` in `main.py`, exposing
  `GET /metrics` (latency/throughput histograms per route, in Prometheus's
  own format) for anything that scrapes it. Active-user counts and queue
  depth still aren't derived anywhere — that part is genuinely open if a
  dashboard needs them.

## P2 — untouched (correctly deprioritized)

Workspace abstraction, billing, team collaboration, advanced analytics —
all correctly last per the original review ("don't build team
collaboration until personal multi-tenancy is stable"). Nothing here
until the P1 list above is clear.

## README/docs

Fixed the stale "AI runs locally, no data leaves the machine" claim in
`README.md` and `ARCHITECTURE.md` — the deployed backend calls OpenRouter
for every AI request (`ai/ollama_client.py`); there's no local-model
fallback wired up yet, so the privacy story now says that plainly instead
of promising something the current build doesn't do.
