# Google Calendar Integration — Milestone 6

Turns `GET/POST /api/calendar/*` from `501` into real sync endpoints.
The integration is **opt-in**: the app runs fine unconfigured (every
other milestone's features keep working) and degrades gracefully if
`credentials.json` isn't present yet.

> Todoist sync (originally also part of Milestone 6) was removed after
> the external API changed and stopped being worth the maintenance cost.
> Brain Dump now ships its own native task manager instead of relying on
> a third-party task service — see the project roadmap for the native
> task manager work that replaced it.

## One-time local setup

**Google Calendar** — needs a (free) OAuth client:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) ->
   create a project (or reuse one) -> enable the **Google Calendar API**.
2. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   -> Application type **Desktop app**.
3. Download the JSON, save it as `credentials.json` in the `ai_os/` root
   (next to `.env`, `data/`, etc — see `backend/config.py::GOOGLE_CREDENTIALS_PATH`).
4. The first time any calendar endpoint runs, a browser tab opens for
   one-time consent; `token.json` is written afterward and silently
   refreshed on every run after that. Both files are git-ignored.
5. While the OAuth consent screen is in "Testing" publishing status
   (the default for a new project), only accounts added under **Test
   users** can complete the consent flow — anyone else gets an
   `access_denied` / "app has not completed verification" error. Add
   your own Google account there before testing.

No billing setup is required for the Calendar API's free tier at
personal-use volume.

## What's live

- **`backend/integrations/google_calendar.py`** — OAuth (`_load_credentials()`
  / `get_service()`, lazy + cached per process), `list_events()` (full
  event details for caching), `get_free_busy()` (busy intervals only, via
  the dedicated `freebusy` endpoint), `create_event()` / `update_event()`
  / `delete_event()`. All-day vs timed events are normalized to UTC-aware
  datetimes in one place (`_parse_event_datetime()`) so nothing downstream
  special-cases Google's two shapes.
- **`backend/services/calendar_sync_service.py`** — `pull_google_events()`
  upserts real events into `CalendarEvent` as `source=GOOGLE`, matched by
  `google_event_id`, and removes locally-cached ones no longer present
  remotely. `push_pending_sessions()` pushes `source=BRAIN_DUMP` rows the
  scheduler already created up to Google. `push_single_event()` is the
  on-demand "Start Timer now" path. `sync_calendar()` is the combined pass.
- **`api/calendar.py`** — `GET /events` (local cache, optional
  `?source=` filter), `POST /sync`, `POST /create-session`.
- **`backend/scheduler/morning.py`** / **`nightly.py`** — call
  `sync_calendar()` / `push_pending_sessions()` around the existing
  scheduling/replan steps, wrapped so a not-yet-configured integration
  only skips that one step (logged at `info`, not an error).

## Design decisions

- **`api/calendar.py` lets an unconfigured `/sync` call raise all the way
  to a `424`.** Calendar sync is the primary reason someone hits that
  endpoint, so failing loudly when `credentials.json` is missing is more
  useful than silently no-op'ing.
- **`push_single_event()` never leaves an orphaned local row.** If Google
  Calendar isn't configured, the `CalendarEvent` is still committed
  locally (`sync_status=NOT_SYNCED`) rather than failing the whole
  "Start Timer" action — the scheduler already treats `BRAIN_DUMP` rows as
  real busy time regardless of `sync_status`, so the feature degrades to
  "local-only, syncs later" instead of blocking the user.
- **`get_free_busy()` uses the dedicated `freebusy` endpoint, `list_events()`
  uses `events().list()`.** They overlap in purpose but not cost: freebusy
  is the cheaper call when only start/end matters (a future
  `scheduler_service` optimization could call it directly instead of
  `list_events()` if event titles turn out not to be needed there), while
  `list_events()` is what actually gets cached locally since the local
  `CalendarEvent.title` field needs real event titles, not just intervals.

## Verified

With the `google_calendar` module monkeypatched (no live network access
in this environment — real API calls need a genuine `credentials.json`/
OAuth consent, a one-time manual step for whoever runs this for real):
simulated `pull_google_events()` upserting new events and removing a
stale one, and `push_pending_sessions()` pushing a `NOT_SYNCED` row and
marking it `SYNCED`. Also ran the full app through `TestClient` and
confirmed `GET /api/calendar/events` and `POST /api/calendar/sync` (424
with no `credentials.json` present) behave as designed instead of the
old blanket `501`.

## Next milestone

**Milestone 7 — Next.js frontend**: the dashboard, Brain Dump input,
Projects/Calendar/Analytics pages, and the AI Chat surface. Calendar now
has real data to show — `GET /api/calendar/events` and the sync
endpoints above are what the Calendar page and a "Sync now" button call.
