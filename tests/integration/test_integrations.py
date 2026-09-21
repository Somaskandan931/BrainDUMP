"""Per-user Google Calendar: credential storage, the OAuth connect/callback flow, and sync."""

from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from backend.app.core import config
from backend.app.auth import security
from backend.app.db.database import SessionLocal, owner_id
from backend.app.integrations import google_calendar
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.enums import EventSource, SyncStatus
from backend.app.models.settings import Setting
from backend.app.services.integrations import calendar_sync_service, integration_credentials_service as creds
from tests.helpers import make_task, make_user, scoped_session, utcnow

_STATE_PURPOSE = "google_calendar_oauth"
_GOOD_CREDENTIALS = json.dumps({"token": "at", "refresh_token": "rt", "client_id": "c", "client_secret": "s"})


@pytest.fixture()
def other_user():
    return make_user("other@example.com")


@pytest.fixture()
def other_db(other_user):
    session = scoped_session(other_user)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def oauth_configured(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config, "FRONTEND_URL", "http://frontend.test")


def _stored_raw(user_id: int) -> str | None:
    with SessionLocal() as everyone:
        row = everyone.query(Setting).filter(Setting.user_id == user_id, Setting.key == "integration_google_credentials").first()
        return row.value if row else None


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------

def test_credentials_are_per_user(db, other_db):
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)

    assert creds.get_google_credentials_json(db) == _GOOD_CREDENTIALS
    assert creds.has_google_credentials(db) and not creds.has_google_credentials(other_db)
    assert creds.get_google_credentials_json(other_db) is None


def test_saving_twice_overwrites_and_clearing_forgets(db):
    creds.save_google_credentials_json(db, "one")
    creds.save_google_credentials_json(db, "two")
    assert creds.get_google_credentials_json(db) == "two"
    assert db.query(Setting).filter(Setting.key == "integration_google_credentials").count() == 1

    assert creds.clear_google_credentials(db) is True
    assert creds.clear_google_credentials(db) is False
    assert creds.get_google_credentials_json(db) is None


def test_credentials_are_encrypted_at_rest_when_a_key_is_configured(db, user, monkeypatch):
    monkeypatch.setattr(config, "INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())

    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)

    raw = _stored_raw(user.id)
    assert raw.startswith("enc:")
    assert "refresh_token" not in raw and '"rt"' not in raw and _GOOD_CREDENTIALS not in raw
    assert creds.get_google_credentials_json(db) == _GOOD_CREDENTIALS


def test_wrong_or_missing_key_reads_as_not_connected_not_as_a_crash(db, monkeypatch):
    monkeypatch.setattr(config, "INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)

    monkeypatch.setattr(config, "INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())  # rotated/wrong
    assert creds.get_google_credentials_json(db) is None
    monkeypatch.setattr(config, "INTEGRATION_ENCRYPTION_KEY", "")
    assert creds.get_google_credentials_json(db) is None


def test_plaintext_row_written_before_a_key_existed_still_reads_back(db, monkeypatch):
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)  # no key: stored plaintext
    monkeypatch.setattr(config, "INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert creds.get_google_credentials_json(db) == _GOOD_CREDENTIALS


def test_get_service_requires_connected_credentials():
    with pytest.raises(google_calendar.GoogleCalendarNotConfigured):
        google_calendar.get_service_for_user(None)


# ---------------------------------------------------------------------------
# /api/calendar/google/*
# ---------------------------------------------------------------------------

def test_status_reports_server_and_user_state(client, db, monkeypatch, oauth_configured):
    assert client.get("/api/calendar/google/status").json() == {"oauth_client_configured": True, "connected": False}

    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)
    assert client.get("/api/calendar/google/status").json()["connected"] is True

    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_ID", "")
    assert client.get("/api/calendar/google/status").json()["oauth_client_configured"] is False


def test_connect_without_a_configured_oauth_client_is_424(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_ID", "")
    res = client.get("/api/calendar/google/connect")
    assert res.status_code == 424 and "GOOGLE_CALENDAR_CLIENT_ID" in res.json()["detail"]


def test_connect_returns_a_google_url_carrying_a_state_for_this_user(client, user, oauth_configured):
    url = client.get("/api/calendar/google/connect").json()["authorization_url"]
    query = parse_qs(urlparse(url).query)

    assert urlparse(url).netloc == "accounts.google.com"
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]  # what yields a refresh token
    assert "code_challenge" not in query  # PKCE would break the separate-request code exchange
    assert security.decode_state_token(query["state"][0], _STATE_PURPOSE) == user.id


def test_callback_stores_credentials_for_the_user_named_in_state_only(
    anon_client, user, other_user, db, other_db, oauth_configured, monkeypatch
):
    monkeypatch.setattr(google_calendar, "exchange_code", lambda code: _GOOD_CREDENTIALS if code == "the-code" else "x")
    state = security.create_state_token(user.id, _STATE_PURPOSE)

    res = anon_client.get(
        "/api/calendar/google/callback", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert res.status_code == 303
    assert res.headers["location"] == "http://frontend.test/settings?calendar=connected"
    assert creds.get_google_credentials_json(db) == _GOOD_CREDENTIALS
    assert creds.get_google_credentials_json(other_db) is None


@pytest.mark.parametrize(
    "case",
    ["no_code", "google_error", "garbage_state", "expired_state", "wrong_purpose", "access_token_as_state", "no_refresh_token", "exchange_fails", "inactive_user"],
)
def test_callback_failures_redirect_to_an_error_and_save_nothing(anon_client, user, db, oauth_configured, monkeypatch, case):
    from backend.app.models.user import User

    state = security.create_state_token(user.id, _STATE_PURPOSE)
    params = {"code": "c", "state": state}
    exchange = lambda code: _GOOD_CREDENTIALS  # noqa: E731

    if case == "no_code":
        params.pop("code")
    elif case == "google_error":
        params = {"error": "access_denied", "state": state}
    elif case == "garbage_state":
        params["state"] = "not-a-jwt"
    elif case == "expired_state":
        params["state"] = security.create_state_token(user.id, _STATE_PURPOSE, expires_minutes=-1)
    elif case == "wrong_purpose":
        params["state"] = security.create_state_token(user.id, "something_else")
    elif case == "access_token_as_state":
        params["state"] = security.create_access_token(user.id)
    elif case == "no_refresh_token":
        exchange = lambda code: json.dumps({"token": "at"})  # noqa: E731
    elif case == "exchange_fails":
        def exchange(code):
            raise google_calendar.GoogleCalendarError("Google said no")
    elif case == "inactive_user":
        with SessionLocal() as s:
            s.get(User, user.id).is_active = False
            s.commit()

    monkeypatch.setattr(google_calendar, "exchange_code", exchange)

    res = anon_client.get("/api/calendar/google/callback", params=params, follow_redirects=False)

    assert res.status_code == 303 and res.headers["location"].endswith("/settings?calendar=error")
    assert creds.get_google_credentials_json(db) is None


def test_disconnect_forgets_credentials_and_cached_google_events_for_this_user_only(
    client, db, other_db, other_user
):
    for session in (db, other_db):
        creds.save_google_credentials_json(session, _GOOD_CREDENTIALS)
        for source in (EventSource.GOOGLE, EventSource.BRAIN_DUMP):
            session.add(
                CalendarEvent(
                    user_id=owner_id(session), title=source.value, start_time=utcnow(), end_time=utcnow(),
                    source=source, sync_status=SyncStatus.SYNCED, synced=True,
                )
            )
        session.commit()

    assert client.delete("/api/calendar/google").status_code == 204

    assert not creds.has_google_credentials(db)
    assert [e.source for e in db.query(CalendarEvent).all()] == [EventSource.BRAIN_DUMP]  # own sessions kept
    assert creds.has_google_credentials(other_db)
    assert db.query(CalendarEvent).count() == 1 and other_db.query(CalendarEvent).count() == 2


def test_sync_endpoint_is_424_until_the_user_connects(client, oauth_configured):
    res = client.post("/api/calendar/sync")
    assert res.status_code == 424 and "connect" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Sync service (Google itself faked)
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_google(monkeypatch):
    """Google's API replaced by an in-memory calendar; records what was created."""

    class Fake:
        remote_events: list = []
        created: list = []
        refreshed_json: str | None = None

    fake = Fake()
    fake.remote_events, fake.created = [], []

    monkeypatch.setattr(google_calendar, "get_service_for_user", lambda credentials_json: (object(), fake.refreshed_json))
    monkeypatch.setattr(google_calendar, "list_events", lambda service, start, end: list(fake.remote_events))

    def create_event(service, title, start, end, description=None):
        fake.created.append(title)
        return f"created-{len(fake.created)}"

    monkeypatch.setattr(google_calendar, "create_event", create_event)
    return fake


def _remote(event_id: str, title: str = "Meeting"):
    start = utcnow() + timedelta(hours=2)
    return {"google_event_id": event_id, "title": title, "start": start, "end": start + timedelta(hours=1)}


def test_two_users_syncing_the_same_meeting_each_get_their_own_row(db, other_db, fake_google):
    fake_google.remote_events = [_remote("shared-meeting")]
    for session in (db, other_db):
        creds.save_google_credentials_json(session, _GOOD_CREDENTIALS)

    assert calendar_sync_service.sync_calendar(db)["pulled"] == 1
    assert calendar_sync_service.sync_calendar(other_db)["pulled"] == 1  # used to be an IntegrityError

    assert db.query(CalendarEvent).count() == 1 and other_db.query(CalendarEvent).count() == 1


def test_pull_updates_existing_rows_and_removes_events_deleted_on_google(db, fake_google):
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)
    fake_google.remote_events = [_remote("a", "Old title"), _remote("b")]
    calendar_sync_service.sync_calendar(db)

    fake_google.remote_events = [_remote("a", "New title")]  # "b" was deleted on Google
    result = calendar_sync_service.sync_calendar(db)

    assert result["pulled"] == 1 and result["removed"] == 1
    assert [e.title for e in db.query(CalendarEvent).all()] == ["New title"]


def test_push_sends_this_users_pending_sessions_to_google_and_marks_them_synced(db, other_db, fake_google):
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)
    mine, theirs = make_task(db, "my session"), make_task(other_db, "their session")
    for session, task in ((db, mine), (other_db, theirs)):
        session.add(
            CalendarEvent(
                user_id=owner_id(session), task_id=task.id, title=task.title, start_time=utcnow(),
                end_time=utcnow() + timedelta(hours=1), source=EventSource.BRAIN_DUMP,
                sync_status=SyncStatus.NOT_SYNCED, synced=False,
            )
        )
        session.commit()

    pushed, errors = calendar_sync_service.push_pending_sessions(db)

    assert (pushed, errors) == (1, [])
    assert fake_google.created == ["my session"]  # never the other user's
    assert db.query(CalendarEvent).one().sync_status == SyncStatus.SYNCED
    assert other_db.query(CalendarEvent).one().sync_status == SyncStatus.NOT_SYNCED


def test_a_refreshed_access_token_is_persisted_for_the_next_call(db, fake_google):
    creds.save_google_credentials_json(db, _GOOD_CREDENTIALS)
    fake_google.refreshed_json = json.dumps({"token": "NEW", "refresh_token": "rt"})

    calendar_sync_service.pull_google_events(db)

    assert json.loads(creds.get_google_credentials_json(db))["token"] == "NEW"


def test_sync_for_a_user_who_never_connected_raises_not_configured(db):
    with pytest.raises(google_calendar.GoogleCalendarNotConfigured):
        calendar_sync_service.pull_google_events(db)


def test_starting_a_session_still_works_locally_when_calendar_is_not_connected(db):
    task = make_task(db, "work")
    event = calendar_sync_service.push_single_event(db, task, utcnow(), utcnow() + timedelta(hours=1))

    assert event.id and event.user_id == task.user_id
    assert event.google_event_id is None and event.sync_status == SyncStatus.NOT_SYNCED
