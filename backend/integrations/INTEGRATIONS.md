# Google Calendar and Todoist Integrations — Milestone 6

Turns `GET/POST /api/calendar/*` and `GET/POST /api/todoist/*` from `501`
into real sync endpoints. Both integrations are **opt-in**: the app runs
fine with neither configured (every other milestone's features keep
working), and each degrades independently if only one is set up.

## One-time local setup

**Todoist** — the easy one, no app registration:
1. Todoist -> Settings -> Integrations -> Developer -> copy your API token.
2. Copy `.env.example` to `.env` in the `ai_os/` root, set `TODOIST_API_TOKEN=...`.

**Google Calendar** — needs a (free) OAuth client, since Google doesn't
offer a personal-token option like Todoist:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) ->
   create a project (or reuse one) -> enable the **Google Calendar API**.
2. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   -> Application type **Desktop app**.
3. Download the JSON, save it as `credentials.json` in the `ai_os/` root
   (next to `.env`, `data/`, etc — see `backend/config.py::GOOGLE_CREDENTIALS_PATH`).
4. The first time any calendar endpoint runs, a browser tab opens for
   one-time consent; `token.json` is written afterward and silently
   refreshed on every run after that. Both files are git-ignored.

Neither service costs anything at personal-use volume — no billing setup
required for the Calendar API's free tier, and Todoist's REST API is free
for any account tier.

## What's live

- **`backend/integrations/google_calendar.py`** — OAuth (`_load_credentials()`
  / `get_service()`, lazy + cached per process), `list_events()` (full
  event details for caching), `get_free_busy()` (busy intervals only, via
  the dedicated `freebusy` endpoint), `create_event()` / `update_event()`
  / `delete_event()`. All-day vs timed events are normalized to UTC-aware
  datetimes in one place (`_parse_event_datetime()`) so nothing downstream
  special-cases Google's two shapes.
- **`backend/integrations/todoist.py`** — REST API v2 wrapper: `pull_tasks()`,
  `push_task()`, `update_task()`, `close_task()`, `delete_task()`, plus
  `importance_to_priority()` / `priority_to_importance()` mapping Brain
  Dump's `Importance` enum to Todoist's 1 (normal) - 4 (urgent) scale.
- **`backend/services/calendar_sync_service.py`** — `pull_google_events()`
  upserts real events into `CalendarEvent` as `source=GOOGLE`, matched by
  `google_event_id`, and removes locally-cached ones no longer present
  remotely. `push_pending_sessions()` pushes `source=BRAIN_DUMP` rows the
  scheduler already created up to Google. `push_single_event()` is the
  on-demand "Start Timer now" path. `sync_calendar()` is the combined pass.
- **`backend/services/todoist_sync_service.py`** — keyed on the new
  `Task.todoist_id` column (see below). `pull_todoist_tasks()` imports new
  remote items as local Tasks and completes local Tasks whose linked
  Todoist item disappeared (closed/deleted on the Todoist side).
  `push_pending_tasks()` creates Todoist items for unlinked local Tasks
  and closes the Todoist item for Tasks completed here. `sync_todoist()`
  is the combined pass, pull-before-push so a phone-completed task isn't
  double-pushed.
- **`api/calendar.py`** — `GET /events` (local cache, optional
  `?source=` filter), `POST /sync`, `POST /create-session`.
- **`api/todoist.py`** — `GET /tasks` (live read-through to Todoist, not
  the cache — there is no local Todoist-item cache, only linked `Task`
  rows), `POST /sync`, `POST /push-task`.
- **`backend/models/task.py`** — added `todoist_id: Optional[str]`
  (nullable, unique) for two-way reconciliation.
- **`backend/scheduler/morning.py`** / **`nightly.py`** — now call
  `sync_calendar()` / `push_pending_sessions()` / `sync_todoist()` around
  the existing scheduling/replan steps, each wrapped so a not-yet-configured
  integration only skips that one step (logged at `info`, not an error).

## Design decisions

- **Two different "not configured" experiences, on purpose.** Google
  Calendar's `GoogleCalendarNotConfigured` and Todoist's
  `TodoistNotConfigured` both subclass their integration's base error, but
  the API layer treats them differently: `api/calendar.py` lets an
  unconfigured `/sync` call raise all the way to a `424` (calendar sync is
  the primary reason someone hits that endpoint), while
  `todoist_sync_service.sync_todoist()` catches its own "not configured"
  case internally and reports it as an `errors` entry in a normal `200` —
  because Todoist and Calendar sync are independent, and a `POST /sync`
  someone expects to also touch Calendar shouldn't 424 outright just
  because Todoist isn't set up too. The single-item `POST /push-task` is
  the exception on the Todoist side: an explicit "push this one task" ask
  fails loudly (`424`/`502`), same as Calendar's `/sync`.
- **`push_single_event()` never leaves an orphaned local row.** If Google
  Calendar isn't configured, the `CalendarEvent` is still committed
  locally (`sync_status=NOT_SYNCED`) rather than failing the whole
  "Start Timer" action — the scheduler already treats `BRAIN_DUMP` rows as
  real busy time regardless of `sync_status`, so the feature degrades to
  "local-only, syncs later" instead of blocking the user.
- **No local cache table for Todoist items.** Google Calendar gets a local
  `CalendarEvent` cache because the scheduler needs to query busy time
  fast and often (every planning pass). Todoist tasks don't have an
  equivalent hot path — `pull_todoist_tasks()` either creates a real local
  `Task` (once) or does nothing, so a separate cache table would just be
  duplicate state to keep in sync with itself.
- **Reconciliation is one-directional-per-field, not last-write-wins on
  everything.** `pull_todoist_tasks()` only ever creates new local `Task`s
  or completes them — it never overwrites title/deadline/importance on an
  already-linked task from the remote side, since Brain Dump's own AI
  pipeline (estimation, priority scoring) owns those fields going forward.
  Todoist stays the *inbox*, not a competing source of truth once a task
  is linked.
- **No SQLAlchemy migrations exist yet (no Alembic in this project).**
  `Task.todoist_id` is a new column on an existing table. `init_db()`'s
  `Base.metadata.create_all()` only creates tables that don't exist — it
  does **not** alter existing ones. On a fresh checkout this is invisible
  (the table is created with the column from day one). On a machine that
  already ran Milestones 1-5 and has a populated `data/tasks.db`, either
  delete that file and let `init_db()` recreate it (fine for personal,
  early-stage data) or run a manual `ALTER TABLE tasks ADD COLUMN
  todoist_id VARCHAR(64)` before starting the app. Worth revisiting when
  Milestone 9 (testing/Docker) looks at the project's total lack of a
  migration tool.
- **Todoist due dates are date-only (`due_date`), not `due_datetime`.**
  Brain Dump deadlines are "Assignment due 30 July" (a day), not a
  specific minute — matching Todoist's simpler `due_date` field avoids
  inventing a fake time-of-day that would show up misleadingly in the
  Todoist app.
- **`get_free_busy()` uses the dedicated `freebusy` endpoint, `list_events()`
  uses `events().list()`.** They overlap in purpose but not cost: freebusy
  is the cheaper call when only start/end matters (a future
  `scheduler_service` optimization could call it directly instead of
  `list_events()` if event titles turn out not to be needed there), while
  `list_events()` is what actually gets cached locally since the local
  `CalendarEvent.title` field needs real event titles, not just intervals.

## Verified

With `google_calendar` and `todoist` modules monkeypatched (no live
network access in this environment — real API calls need a genuine
`credentials.json`/OAuth consent and a live Todoist token, which is a
one-time manual step for whoever runs this for real): simulated
`pull_google_events()` upserting new events and removing a stale one,
`push_pending_sessions()` pushing a `NOT_SYNCED` row and marking it
`SYNCED`, `pull_todoist_tasks()` creating a new local `Task` from a remote
item and completing a local `Task` whose linked remote item disappeared,
and `push_pending_tasks()` creating a Todoist item for an unlinked task
and closing one for a completed, linked task. Also ran the full app
through `TestClient` and confirmed `GET /api/calendar/events`,
`POST /api/calendar/sync` (424 with no `credentials.json` present),
`GET /api/todoist/tasks` and `POST /api/todoist/sync` (200 with an
`errors` entry, no token set) all behave as designed instead of the old
blanket `501`.

## Next milestone

**Milestone 7 — Next.js frontend**: the dashboard, Brain Dump input,
Projects/Calendar/Analytics pages, and the AI Chat surface. Calendar and
Todoist now have real data to show — `GET /api/calendar/events` and the
sync endpoints above are what the Calendar page and a "Sync now" button
call.
