# Brain Dump — multi-user auth refactor

State of the multi-user refactor. Backend suite: **158 tests passing**
(`python -m pytest`); frontend `tsc --noEmit` and `next lint` clean.

## What's in place

- **Accounts:** email/password + Google Sign-In (`backend/models/user.py`,
  `backend/auth/`, `backend/api/auth.py`, `backend/api/deps.py`). JWT bearer
  tokens; deactivated users are locked out of existing tokens.
- **Row-level isolation:** `user_id` on every tenant-owned table, enforced by a
  SQLAlchemy `do_orm_execute` filter (`backend/database.py`). Every insert stamps
  `user_id=owner_id(db)`; `owner_id()` raises on an unscoped session.
- **Every `/api` route requires auth** except `/api/auth/register|login|google`,
  `/health`, and the Google OAuth callback (which authenticates via a signed
  `state`). `tests/test_auth.py` fails if a new route is added unprotected.
- **Per-user Google Calendar:** web OAuth flow, tokens stored per user on the
  `settings` table, encrypted at rest with `INTEGRATION_ENCRYPTION_KEY`
  (`backend/integrations/google_calendar.py`,
  `backend/services/integration_credentials_service.py`,
  `backend/api/calendar.py`, `INTEGRATIONS.md`). Settings page has a
  "Connect Google Calendar" card.
- **Background jobs** (`scheduler/morning.py`, `nightly.py`) run once per active
  user. The Sunday estimator retrain stays a single pooled run.
- **Migrations:** `0003`/`0004` (users + `user_id`), `0005` (`google_event_id`
  unique per user).
- **Tests:** `test_auth.py`, `test_tenant_isolation.py`, `test_integrations.py`,
  plus the existing suite moved onto a per-test user.

## Bugs found and fixed while finishing this

| Bug | Impact | Fix |
|---|---|---|
| Tenant filter used `lambda cls, uid=user_id: ...`; SQLAlchemy caches lambda criteria and only tracks *closure* variables, so the first user's id was frozen in for the whole process | **Every user after the first saw the first user's data** | `database.py`: pass a plain boolean expression instead of a lambda, which never enters the lambda cache. Guarded by `test_tenant_isolation.py` |
| `passlib[bcrypt]` unpinned pulls bcrypt 5.x; passlib 1.7.4 can't hash with it | Registration/login failed on any fresh install | `bcrypt==4.0.1` pinned in `requirements.txt` |
| Migration `0003`'s placeholder user violated `ck_users_has_login_method` | Any populated pre-auth database failed to upgrade at boot | Placeholder gets a `google_sub` no real account can match |
| Migration `0004` left `daily_plans.plan_date` globally unique, and required a placeholder user even when nothing needed backfilling | Second user couldn't start their day on the same date; some upgrades raised | Index made non-unique; placeholder looked up lazily |
| `users.google_sub` was a unique index in the migration but a constraint in the model | Migration/model drift | `0003` creates the constraint |
| `calendar_events.google_event_id` globally unique | Two attendees of one meeting collided on sync | Unique per `(user_id, google_event_id)` (`0005`) |
| Google OAuth URL carried a PKCE challenge the callback's fresh `Flow` couldn't satisfy | Every token exchange would have been rejected | PKCE autogeneration disabled |
| `POST/PUT /api/tasks` accepted another user's `project_id` | Task could reference someone else's project | 404 unless the project is the caller's |
| Morning job's calendar push was unguarded | A user without Google connected lost their whole morning run | Guarded like the nightly push |
| `usePathname()` can be `null` (Next 14) in `AppShell`/`RouteGuard` | `next build` type error | `?? ""` |
| `POST /api/auth/google` auto-linked Google onto any existing email/password account with the same email, and registration doesn't verify email | Pre-hijack: attacker registers a victim's address, keeps password access after the victim signs in with Google | Google sign-in now refuses to link (409, "sign in with your password"); `test_auth.py` covers the scenario |
| No limit on login/register/Google attempts | `/api/auth/login` could be brute-forced | `auth/rate_limit.py`: 429 + `Retry-After` (failures per IP+email and per IP; registrations and Google attempts per IP). Env-tunable, see `config.py` |
| Login skipped password hashing for unknown emails; emails matched case-sensitively | Response time revealed which emails are registered; `Foo@x.com` and `foo@x.com` were different accounts | Same hashing cost either way; emails matched case-insensitively and stored lowercase |
| `GoogleButton` swallowed every sign-in error | Failed Google sign-in (409, 429, deactivated) did nothing visible | `onError` wired to the login/register pages |
| Deploy backend ran uvicorn without `--proxy-headers` | Behind Render every client shared one IP, collapsing per-IP rate limits into one bucket | Added `--proxy-headers --forwarded-allow-ips='*'` to the deploy Dockerfile |
| Deploy-kit overlay predated auth (no auth router, no JWT config, no auth deps) | Following `DEPLOY.md` would have shipped a broken app | Overlay rebuilt from the current backend; Render env vars updated |

## Removed (dead code)

The Todoist sync layer — `integrations/todoist.py`, `services/todoist_sync_service.py`,
`api/todoist.py`, `schemas/todoist.py`, its router registration and config. It
referenced `Task.todoist_id`, which migration `0002` deliberately dropped, so
every sync/push call would have raised `AttributeError`. Also removed unused
imports (including `owner_id` from eight routers that never used it).

## Known follow-ups (not done)

- **Real Google OAuth end-to-end** has not been run: tests fake Google. It needs a
  real Web OAuth client and one manual pass (see `INTEGRATIONS.md`).
- **`next build`** wasn't verified in the sandbox (no access to Google Fonts);
  `tsc` and `next lint` pass.
- **Password accounts can't add Google later.** Refusing to auto-link closes the
  pre-hijack hole, but a user who registered with a password and then clicks
  "Sign in with Google" is told to use their password. A proper "link Google"
  action (signed in *and* Google-verified) needs a Settings UI; real email
  verification / password reset would need an email provider.
- **Rate limiting is in-memory and per process.** It resets on restart and isn't
  shared across instances, and a distributed attack (many IPs, one account) isn't
  covered. Fine for one API process; swap the store for Redis if you scale out.
- **Pre-auth data is orphaned.** Upgrading an existing DB assigns all existing rows
  to the inactive `legacy@local` placeholder, which nobody can log into, so they
  are invisible. Fine for throwaway dev data; if any of it matters, add a
  "claim legacy data" step.
- `google_calendar.get_free_busy()` and `delete_event()` have no callers; kept as
  part of the wrapper's API.
- SQLite on Render's free plan is ephemeral, so accounts and stored Google tokens
  reset on redeploy (see `DEPLOY-FREE.md`).
