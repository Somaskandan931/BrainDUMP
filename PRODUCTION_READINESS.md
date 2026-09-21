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

- **Email verification** — `users.is_verified` (migration `0008`),
  `services/email_service.py` (SMTP if configured, logs the email
  otherwise so local dev needs zero setup), `/api/auth/verify-email/{resend,confirm}`.
  Gated behind `config.EMAIL_VERIFICATION_REQUIRED` (default off) so
  turning it on is a deliberate production step, not a breaking default.
- **Password reset** — `/api/auth/password-reset/{request,confirm}`,
  same anti-enumeration shape as login (identical response whether or
  not the email is registered). Reuses the existing purpose-scoped JWT
  mechanism (`auth/security.py`'s `create_state_token` /
  `decode_state_token`) instead of a new token table.
- Frontend: `/forgot-password`, `/reset-password`, `/verify-email` pages;
  a "Forgot password?" link and resend-verification affordance on `/login`.
- 9 new backend tests (`tests/security/test_auth.py`); full suite is
  170/170 green.

### Known limitation worth knowing about

Reset/verification tokens are JWTs with an expiry (30 min / 24h) but are
**not single-use** — nothing invalidates a token after it's been redeemed
once, so a captured-but-unused link stays valid until it expires on its
own. Fine for the current threat model (short expiry, HTTPS-only,
one-time email delivery), but if this becomes a compliance requirement,
the fix is a small `used_at` column or a Redis SETNX on the token's `jti`,
not a redesign.

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
  - **Frontend:** typed client only (`activityApi`, `tasksApi.history`,
    `ActivityItem`/`DeadlineChangedDetails` in `services/types.ts`). There is
    no UI for it yet — the "why did this move?" panel is the natural next piece.
  - **Known limits:** a replan repacks the whole schedule, and per-task rows
    for every repacked task every night would be N rows/user/night, so only
    *deadline* moves are per-task; the repack itself is one
    `schedule.replanned` row (written only when something changed) listing the
    demoted/at-risk task ids. A chat-triggered replan (`ai_coach_service`) is
    attributed to `user`, since the user asked for it.
  - 63 new tests (`tests/unit/test_activity_log.py`,
    `tests/integration/test_activity_api.py`); full suite is 263/263 green.

## P0 — still open

- **Production auth cookie/session model** — the JWT still travels in
  `localStorage` (`frontend/services/api.ts`), not an HttpOnly cookie.
  Fine for a single-domain deployment, but XSS-exposed either way; moving
  to HttpOnly + SameSite is a frontend + CORS-config change, not done here.
- **Short-lived access tokens + refresh rotation** — `JWT_EXPIRE_MINUTES`
  defaults to 7 days with no refresh/revocation path. Lower priority than
  it looks: there's no session list or "log out everywhere" UI yet either,
  so refresh rotation without that is partial credit.

## P1 — still open

- **AI usage limits** — already done (`services/ai/usage_service.py`,
  `config.AI_DAILY_CALL_LIMIT`), not open.
- **Demo mode** — `api/v1/demo.py` + `services/workspace/demo_service.py`
  already seed/reset a workspace for the current authenticated user; this
  covers the "let a recruiter click around" need without a separate
  public demo account. Not open.
- **Metrics** (API/AI latency percentiles, queue depth, active-user
  counts as a dashboard, not just log lines) — still open; the structured
  request log above has the raw data a log-based metrics pipeline (or a
  Prometheus middleware) could derive it from, but nothing aggregates it
  yet.

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
