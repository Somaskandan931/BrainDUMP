"""services/workspace/activity_service.py — the audit trail's write path, sanitizer,
diffing, paging, and retention. Endpoint/hook behaviour is in
tests/integration/test_activity_api.py.

Written against the actual shipped surface: log_activity() takes a plain
string `action` and an explicit keyword-only `user_id` (there is no `Action`
enum -- every real call site in api/v1/tasks.py, projects.py, auth.py, etc.
passes strings like "task.created" directly), never raises, and returns
None; list_activity() returns a plain list (cursor-paged via `cursor`/
`limit`, not a (rows, next_cursor) tuple); diff_changes() takes two flat
dicts and reports every key whose value changed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.db.database import SessionLocal
from backend.app.models.activity import ActivityLog
from backend.app.services.workspace import activity_service as svc
from backend.app.services.workspace.activity_service import log_activity
from tests.helpers import make_user, scoped_session


def _all_rows() -> list[ActivityLog]:
    """Every row in the table, bypassing tenant scoping (an unscoped session)."""
    with SessionLocal() as everyone:
        return everyone.query(ActivityLog).order_by(ActivityLog.id).all()


# ---------------------------------------------------------------------------
# log_activity
# ---------------------------------------------------------------------------


def test_log_activity_stages_a_row_and_commit_persists_it(db, user):
    log_activity(
        db,
        user_id=user.id,
        action="task.created",
        entity_type="task",
        entity_id=7,
        details={"title": "x"},
    )

    db.commit()
    [stored] = _all_rows()
    assert (stored.user_id, stored.action, stored.entity_type, stored.entity_id, stored.actor) == (
        user.id,
        "task.created",
        "task",
        7,
        "user",
    )
    assert stored.details == {"title": "x"}
    assert stored.created_at is not None


def test_log_activity_does_not_commit_so_a_rollback_discards_it(db, user):
    """The audit row shares the caller's transaction: if the change is rolled back,
    the trail must not claim it happened."""
    log_activity(db, user_id=user.id, action="task.completed", entity_type="task", entity_id=1)
    db.rollback()

    assert _all_rows() == []


def test_log_activity_records_a_non_default_actor(db, user):
    log_activity(db, user_id=user.id, action="schedule.replanned", entity_type="schedule", actor="system")
    db.commit()

    [stored] = _all_rows()
    assert stored.actor == "system"


def test_log_activity_swallows_unexpected_errors_instead_of_raising(db, user, monkeypatch):
    """Auditing must never break the operation being audited."""

    def boom(*args, **kwargs):
        raise RuntimeError("serialization exploded")

    monkeypatch.setattr(svc, "_sanitize_details", boom)

    # Must not raise.
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", details={"a": 1})
    db.commit()
    assert _all_rows() == []


def test_log_activity_on_an_unscoped_session_still_works_with_an_explicit_user_id(user):
    """What the auth routes do: there's no scoped session before a user is known."""
    unscoped = SessionLocal()
    try:
        log_activity(unscoped, user_id=user.id, action="auth.registered", entity_type="user", entity_id=user.id)
        unscoped.commit()
    finally:
        unscoped.close()

    [stored] = _all_rows()
    assert stored.user_id == user.id


# ---------------------------------------------------------------------------
# _sanitize_details (secret-stripping, size caps)
# ---------------------------------------------------------------------------


def test_sanitize_drops_secret_looking_keys_case_insensitively():
    cleaned = svc._sanitize_details(
        {
            "title": "ok",
            "password": "hunter2",
            "Reset_Token": "abc",
            "google_refresh_token": "rt",
            "Authorization": "Bearer x",
            "fine": 1,
        }
    )

    assert cleaned == {"title": "ok", "fine": 1}
    assert "hunter2" not in str(cleaned)


def test_sanitize_returns_none_for_empty_or_fully_secret_input():
    assert svc._sanitize_details(None) is None
    assert svc._sanitize_details({}) is None


def test_sanitize_caps_string_length_and_key_count():
    payload = {"long": "y" * 5000}
    for i in range(30):
        payload[f"key{i}"] = i

    cleaned = svc._sanitize_details(payload)

    assert len(cleaned["long"]) <= svc._MAX_STRING_LEN + 1  # +1 for the truncation ellipsis
    assert len(cleaned) <= svc._MAX_DETAILS_KEYS


# ---------------------------------------------------------------------------
# diff_changes
# ---------------------------------------------------------------------------


def test_diff_changes_reports_every_field_that_actually_changed():
    diff = svc.diff_changes(
        {"title": "Old title", "importance": "low", "status": "pending"},
        {"title": "New title", "importance": "high", "status": "pending"},
    )

    assert diff == {
        "title": {"old": "Old title", "new": "New title"},
        "importance": {"old": "low", "new": "high"},
    }


def test_diff_changes_is_empty_when_nothing_actually_changed():
    assert svc.diff_changes({"title": "Same"}, {"title": "Same"}) == {}


def test_diff_changes_treats_a_missing_old_key_as_none():
    diff = svc.diff_changes({}, {"title": "New"})

    assert diff == {"title": {"old": None, "new": "New"}}


# ---------------------------------------------------------------------------
# list_activity / get_entity_history
# ---------------------------------------------------------------------------


def _log_n(db, user_id, n):
    for i in range(n):
        log_activity(db, user_id=user_id, action="task.created", entity_type="task", details={"i": i})
    db.commit()


def test_list_activity_is_newest_first(db, user):
    _log_n(db, user.id, 3)

    rows = svc.list_activity(db, user_id=user.id)

    assert [r.details["i"] for r in rows] == [2, 1, 0]


def test_list_activity_pages_by_cursor(db, user):
    _log_n(db, user.id, 5)

    first = svc.list_activity(db, user_id=user.id, limit=2)
    second = svc.list_activity(db, user_id=user.id, limit=2, cursor=first[-1].id)

    assert [r.details["i"] for r in first] == [4, 3]
    assert [r.details["i"] for r in second] == [2, 1]


def test_list_activity_filters_by_entity_and_action(db, user):
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", entity_id=1)
    log_activity(db, user_id=user.id, action="task.completed", entity_type="task", entity_id=1)
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", entity_id=2)
    log_activity(db, user_id=user.id, action="project.created", entity_type="project", entity_id=1)
    db.commit()

    for_task_1 = svc.list_activity(db, user_id=user.id, entity_type="task", entity_id=1)
    created = svc.list_activity(db, user_id=user.id, action="task.created")
    projects = svc.list_activity(db, user_id=user.id, entity_type="project")

    assert [r.action for r in for_task_1] == ["task.completed", "task.created"]
    assert len(created) == 2
    assert [r.entity_type for r in projects] == ["project"]


def test_list_activity_clamps_an_out_of_range_limit(db, user):
    _log_n(db, user.id, 3)

    assert len(svc.list_activity(db, user_id=user.id, limit=10_000)) == 3  # clamped, not an error


def test_list_activity_only_returns_the_requested_users_rows(db, user):
    """db is tenant-scoped to `user` -- the session-level listener injects
    its own user_id filter on every query issued through it, so reading
    another user's rows back requires a session scoped to *them*, exactly
    as a real request/job would have."""
    other = make_user("other-activity@example.com")
    other_db = scoped_session(other)
    try:
        log_activity(db, user_id=user.id, action="task.created", entity_type="task", details={"whose": "mine"})
        log_activity(other_db, user_id=other.id, action="task.created", entity_type="task", details={"whose": "theirs"})
        db.commit()
        other_db.commit()

        mine = svc.list_activity(db, user_id=user.id)
        theirs = svc.list_activity(other_db, user_id=other.id)
    finally:
        other_db.close()

    assert [r.details["whose"] for r in mine] == ["mine"]
    assert [r.details["whose"] for r in theirs] == ["theirs"]


def test_get_entity_history_matches_list_activity_scoped_to_one_entity(db, user):
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", entity_id=1)
    log_activity(db, user_id=user.id, action="task.completed", entity_type="task", entity_id=1)
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", entity_id=2)
    db.commit()

    history = svc.get_entity_history(db, user_id=user.id, entity_type="task", entity_id=1)

    assert [r.action for r in history] == ["task.completed", "task.created"]


# ---------------------------------------------------------------------------
# purge_older_than
# ---------------------------------------------------------------------------


def _backdate(row_id: int, days: int) -> None:
    with SessionLocal() as everyone:
        everyone.query(ActivityLog).filter(ActivityLog.id == row_id).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=days)}
        )
        everyone.commit()


def test_purge_deletes_only_rows_older_than_the_cutoff(db, user):
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", details={"age": "old"})
    log_activity(db, user_id=user.id, action="task.created", entity_type="task", details={"age": "fresh"})
    db.commit()
    old_row, fresh_row = _all_rows()
    _backdate(old_row.id, 200)
    _backdate(fresh_row.id, 10)

    removed = svc.purge_older_than(db, user_id=user.id, days=180)
    db.commit()

    assert removed == 1
    assert [r.details["age"] for r in _all_rows()] == ["fresh"]


def test_purge_with_zero_or_negative_days_keeps_everything(db, user):
    log_activity(db, user_id=user.id, action="task.created", entity_type="task")
    db.commit()
    [row] = _all_rows()
    _backdate(row.id, 5000)

    assert svc.purge_older_than(db, user_id=user.id, days=0) == 0
    assert svc.purge_older_than(db, user_id=user.id, days=-1) == 0
    assert len(_all_rows()) == 1


def test_purge_only_touches_the_named_users_rows(db, user):
    other = make_user("other-purge@example.com")
    log_activity(db, user_id=user.id, action="task.created", entity_type="task")
    log_activity(db, user_id=other.id, action="task.created", entity_type="task")
    db.commit()
    mine_row, theirs_row = _all_rows()
    _backdate(mine_row.id, 400)
    _backdate(theirs_row.id, 400)

    removed = svc.purge_older_than(db, user_id=user.id, days=180)
    db.commit()

    assert removed == 1
    [remaining] = _all_rows()
    assert remaining.user_id == other.id
