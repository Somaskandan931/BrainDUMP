# Google Calendar Integration

Backs `/api/calendar/*`. The integration is **opt-in and per-user**: the
app runs fine unconfigured (every other feature keeps working), and each
user connects *their own* Google account from Settings. Nothing is shared
between users and there is no `credentials.json` / `token.json` on disk.

> Todoist sync (originally part of this integration) was removed after
> the external API changed and stopped being worth the maintenance cost.
> Brain Dump now ships its own native task manager instead of relying on
> a third-party task service.

## One-time server setup

The *server* needs one Google OAuth client, shared by all users (each user
still consents separately and gets their own tokens):

1. [Google Cloud Console](https://console.cloud.google.com/) -> create a
   project (or reuse one) -> enable the **Google Calendar API**.
2. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   -> Application type **Web application** (not Desktop app).
3. Add `GOOGLE_CALENDAR_REDIRECT_URI` as an **Authorized redirect URI**. It
   must match exactly; locally that's
   `http://localhost:8000/api/calendar/google/callback`.
4. Set these env vars (`.env` locally, the host's env settings when deployed):

   | Variable | Purpose |
   |---|---|
   | `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET` | the OAuth client above; unset = feature off (`/sync` and `/connect` return 424) |
   | `GOOGLE_CALENDAR_REDIRECT_URI` | the callback URL registered in step 3 |
   | `FRONTEND_URL` | where the callback sends the browser afterwards (`/settings?calendar=connected\|error`) |
   | `INTEGRATION_ENCRYPTION_KEY` | Fernet key encrypting each user's stored token. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Unset = stored **unencrypted** (local dev only) |

5. While the consent screen is in "Testing" publishing status (the default
   for a new project), only accounts listed under **Test users** can
   complete consent; anyone else gets `access_denied`. Add your own account
   before testing. Apps requesting the Calendar scope need Google's
   verification before they can be used by the general public.

`GOOGLE_LOGIN_CLIENT_ID` (Sign in with Google) is a *separate* client and
unrelated to Calendar sync.

## How a user connects

1. The SPA calls `GET /api/calendar/google/connect` (authenticated) and gets
   a Google consent-screen URL back, then navigates the browser to it. The
   URL's `state` is a signed 10-minute token naming the user; it carries a
   `purpose` claim, so it can't be replayed as a login token.
2. After consent Google redirects the browser to
   `GET /api/calendar/google/callback`. That request has no `Authorization`
   header, so the user is identified **only** from `state`. The route stores
   their credentials and always redirects to `FRONTEND_URL/settings?calendar=connected`
   or `...=error` (a browser navigation can't usefully show a JSON error).
3. Credentials live on the tenant-scoped `settings` table
   (`services/integration_credentials_service.py`), encrypted if
   `INTEGRATION_ENCRYPTION_KEY` is set. An expired access token is refreshed
   transparently and the new one persisted. If the refresh token is revoked,
   the user sees "reconnect it from Settings".
4. `DELETE /api/calendar/google` disconnects: it deletes the stored
   credentials and the user's cached `source=GOOGLE` events (left behind, they
   would keep blocking scheduler time for a calendar Brain Dump can no longer
   see). Sessions Brain Dump created itself are kept.

The flow requests `access_type=offline` and `prompt=consent` so Google always
returns a refresh token, and deliberately disables PKCE: the auth URL and the
code exchange happen in two different requests, and a code verifier generated
for the first would be gone by the second (Google rejects it with "Missing
code verifier"). This is a confidential client, so PKCE isn't required.

## Which calendar gets synced

`GOOGLE_CALENDAR_ID` (`backend/config.py`) defaults to `"primary"` -- the
primary calendar of whichever Google account each user connects, which is
what you want for a multi-user app. It is a **server-wide** setting: don't
set it to one person's address on a multi-user deployment.

## What's live

- **`backend/integrations/google_calendar.py`** -- the OAuth handshake
  (`build_authorization_url()` / `exchange_code()`), `get_service_for_user()`
  (builds a client from one user's stored credentials, refreshing if needed),
  and the API calls: `list_events()`, `get_free_busy()`, `create_event()`,
  `update_event()`, `delete_event()`, each taking an explicit `service`.
  All-day vs timed events are normalized to UTC-aware datetimes in one place.
  It never touches the database.
- **`backend/services/integration_credentials_service.py`** -- per-user
  credential storage and encryption.
- **`backend/services/calendar_sync_service.py`** -- `pull_google_events()`
  upserts real events into `CalendarEvent` as `source=GOOGLE` (matched by
  `google_event_id`, unique **per user**) and removes ones no longer present
  remotely. `push_pending_sessions()` pushes `source=BRAIN_DUMP` rows the
  scheduler created. `push_single_event()` is the on-demand "Start Timer now"
  path. `sync_calendar()` is the combined pass.
- **`api/calendar.py`** -- `GET /events`, `POST /sync`, `POST /create-session`,
  and `GET /google/status`, `GET /google/connect`, `GET /google/callback`,
  `DELETE /google`.
- **`backend/scheduler/morning.py`** / **`nightly.py`** -- run once per active
  user, calling the sync/push steps around scheduling and replanning. A user
  who hasn't connected Google only skips those steps (logged at `info`).

## Design decisions

- **`api/calendar.py` lets an unconnected `/sync` call raise all the way
  to a `424`.** Calendar sync is the primary reason someone hits that
  endpoint, so failing loudly when the server has no OAuth client, or this
  user hasn't connected, is more useful than silently no-op'ing.
- **`google_event_id` is unique per user, not globally.** Attendees of one
  meeting share its Google event id, so a global constraint made the second
  user's sync fail (migration `0005`).
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

`tests/test_integrations.py` covers this with Google itself faked (there is
no network in the test environment, so the real consent screen and token
exchange are **not** exercised by tests -- that needs a real OAuth client and
one manual end-to-end pass): per-user and encrypted credential storage, the
`/google/*` endpoints including every callback failure path, per-user
pull/push, two users syncing the same meeting, and refreshed-token
persistence.
