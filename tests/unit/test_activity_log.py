"""services/workspace/activity_service.py — the audit trail's write path, sanitizer,
diffing, paging, and retention. Endpoint/hook behaviour is in
tests/integration/test_activity_api.py."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.database import SessionLocal
from backend.app.models.activity import ActivityLog
from backend.app.models.enums import Importance, TaskStatus
from backend.app.services.workspace import activity_service as svc
from backend.app.services.workspace.activity_service import Action, log_activity
from tests.helpers import make_task, make_user, scoped_session, utcnow


def _all_rows() -> list[ActivityLog]:
    """Every row in the table, bypassing tenant scoping (an unscoped session)."""
    with SessionLocal() as everyone:
        return everyone.query(ActivityLog).order_by(ActivityLog.id).all()


# ---------------------------------------------------------------------------
# log_activity
# ---------------------------------------------------------------------------


def test_log_activity_stages_a_row_for_the_sessions_user_and_commit_persists_it(db, user):
    row = log_activity(db, Action.TASK_CREATED, entity_type="task", entity_id=7, details={"title": "x"})

    assert row is not None
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


def test_log_activity_does_not_commit_so_a_rollback_discards_it(db):
    """The audit row shares the caller's transaction: if the change is rolled back,
    the trail must not claim it happened."""
    log_activity(db, Action.TASK_COMPLETED, entity_type="task", entity_id=1)
    db.rollback()

    assert _all_rows() == []


def test_log_activity_without_any_user_returns_none_instead_of_raising():
    unscoped = SessionLocal()
    try:
        assert log_activity(unscoped, Action.TASK_CREATED) is None
        unscoped.commit()
    finally:
        unscoped.close()
    assert _all_rows() == []


def test_log_activity_accepts_an_explicit_user_id_on_an_unscoped_session(user):
    """What the auth routes do: there's no scoped session before a user is known."""
    unscoped = SessionLocal()
    try:
        assert log_activity(unscoped, Action.AUTH_REGISTERED, entity_type="user", entity_id=user.id, user_id=user.id)
        unscoped.commit()
    finally:
        unscoped.close()

    [stored] = _all_rows()
    assert stored.user_id == user.id


@pytest.mark.parametrize("action", ["", "x" * 65])
def test_log_activity_rejects_an_empty_or_over_long_action(db, action):
    assert log_activity(db, action) is None


def test_log_activity_rejects_an_unknown_actor(db):
    assert log_activity(db, Action.TASK_CREATED, actor="admin") is None


def test_log_activity_swallows_unexpected_errors(db, monkeypatch):
    """Auditing must never break the operation being audited."""

    def boom(*args, **kwargs):
        raise RuntimeError("serialization exploded")

    monkeypatch.setattr(svc, "sanitize_details", boom)

    assert log_activity(db, Action.TASK_CREATED, details={"a": 1}) is None
    db.commit()
    assert _all_rows() == []


# ---------------------------------------------------------------------------
# sanitize_details
# ---------------------------------------------------------------------------


def test_sanitize_drops_secret_looking_keys_at_any_depth_case_insensitively():
    cleaned = svc.sanitize_details(
        {
            "title": "ok",
            "password": "hunter2",
            "Reset_Token": "abc",
            "nested": {"google_refresh_token": "rt", "Authorization": "Bearer x", "fine": 1},
            "items": [{"api_key": "k", "keep": True}],
        }
    )

    assert cleaned == {"title": "ok", "nested": {"fine": 1}, "items": [{"keep": True}]}
    assert "hunter2" not in str(cleaned)


def test_sanitize_returns_none_for_empty_input():
    assert svc.sanitize_details(None) is None
    assert svc.sanitize_details({}) is None
    assert svc.sanitize_details({"password": "only-a-secret"}) is None


def test_sanitize_makes_enums_dates_and_odd_types_json_safe():
    cleaned = svc.sanitize_details(
        {
            "importance": Importance.HIGH,
            "when": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            "naive": datetime(2026, 1, 2, 3, 4),
            "day": datetime(2026, 1, 2).date(),
            "nan": math.nan,
            "inf": math.inf,
            "object": object,
        }
    )

    assert cleaned["importance"] == "high"
    assert cleaned["when"] == "2026-01-02T03:04:00+00:00"
    # naive datetimes (what SQLite returns) are UTC in this app; without the
    # offset a browser would parse them as local time
    assert cleaned["naive"] == "2026-01-02T03:04:00+00:00"
    assert cleaned["day"] == "2026-01-02"
    assert cleaned["nan"] is None and cleaned["inf"] is None
    assert isinstance(cleaned["object"], str)


def test_sanitize_caps_string_length_list_length_and_depth():
    cleaned = svc.sanitize_details(
        {"long": "y" * 5000, "many": list(range(500)), "deep": {"a": {"b": {"c": {"d": {"e": 1}}}}}}
    )

    assert len(cleaned["long"]) <= 500
    assert len(cleaned["many"]) == 50
    assert cleaned["deep"]["a"]["b"]["c"] == "…"  # cut off at max depth


def test_sanitize_replaces_an_oversized_payload_with_a_stub():
    payload = {f"key{i}": "z" * 400 for i in range(40)}  # ~16 KB after per-field caps

    cleaned = svc.sanitize_details(payload)

    assert cleaned["truncated"] is True
    assert len(cleaned["keys"]) <= 20


# ---------------------------------------------------------------------------
# diff_changes
# ---------------------------------------------------------------------------


def test_diff_changes_reports_tracked_fields_with_before_and_after(db):
    task = make_task(db, "Old title", importance=Importance.LOW)

    diff = svc.diff_changes(
        task, {"title": "New title", "importance": Importance.HIGH}, tracked=("title", "importance")
    )

    assert diff == {
        "changes": {
            "title": {"from": "Old title", "to": "New title"},
            "importance": {"from": Importance.LOW, "to": Importance.HIGH},
        }
    }


def test_diff_changes_names_untracked_fields_without_copying_their_values(db):
    task = make_task(db, "T", description="secret plans")

    diff = svc.diff_changes(task, {"description": "even more secret plans"}, tracked=("title",))

    assert diff == {"other_fields": ["description"]}
    assert "secret" not in str(diff)


def test_diff_changes_is_empty_when_nothing_actually_changed(db):
    task = make_task(db, "Same", importance=Importance.MEDIUM, status=TaskStatus.PENDING)

    assert svc.diff_changes(task, {"title": "Same", "importance": Importance.MEDIUM}, tracked=("title", "importance")) == {}


def test_diff_changes_treats_naive_and_aware_datetimes_as_equal(db):
    """SQLite returns the stored deadline naive; the request sends it aware. That
    is a no-op edit, not a change."""
    deadline = utcnow().replace(microsecond=0) + timedelta(days=3)
    task = make_task(db, "T")
    task.deadline = deadline.replace(tzinfo=None)  # as it would be read back from SQLite

    assert svc.diff_changes(task, {"deadline": deadline}, tracked=("deadline",)) == {}


# ---------------------------------------------------------------------------
# list_activity
# ---------------------------------------------------------------------------


def _log_n(db, n):
    for i in range(n):
        log_activity(db, Action.TASK_CREATED, details={"i": i})
    db.commit()


def test_list_activity_is_newest_first_and_pages_by_cursor(db):
    _log_n(db, 5)

    first, cursor = svc.list_activity(db, limit=2)
    second, cursor2 = svc.list_activity(db, limit=2, before_id=cursor)
    third, cursor3 = svc.list_activity(db, limit=2, before_id=cursor2)

    assert [r.details["i"] for r in first] == [4, 3]
    assert [r.details["i"] for r in second] == [2, 1]
    assert [r.details["i"] for r in third] == [0]
    assert cursor is not None and cursor2 is not None
    assert cursor3 is None  # last page


def test_list_activity_exact_fit_has_no_phantom_next_page(db):
    _log_n(db, 3)

    rows, cursor = svc.list_activity(db, limit=3)

    assert len(rows) == 3 and cursor is None


def test_list_activity_filters_by_entity_and_action(db):
    log_activity(db, Action.TASK_CREATED, entity_type="task", entity_id=1)
    log_activity(db, Action.TASK_COMPLETED, entity_type="task", entity_id=1)
    log_activity(db, Action.TASK_CREATED, entity_type="task", entity_id=2)
    log_activity(db, Action.PROJECT_CREATED, entity_type="project", entity_id=1)
    db.commit()

    for_task_1, _ = svc.list_activity(db, entity_type="task", entity_id=1)
    created, _ = svc.list_activity(db, action=Action.TASK_CREATED)
    projects, _ = svc.list_activity(db, entity_type="project")

    assert [r.action for r in for_task_1] == ["task.completed", "task.created"]
    assert len(created) == 2
    assert [r.entity_type for r in projects] == ["project"]


def test_list_activity_clamps_an_out_of_range_limit(db):
    _log_n(db, 3)

    assert len(svc.list_activity(db, limit=0)[0]) == 1
    assert len(svc.list_activity(db, limit=10_000)[0]) == 3  # clamped to MAX_PAGE_SIZE, not an error


def test_list_activity_only_returns_the_callers_rows(db):
    other = make_user("other@example.com")
    other_db = scoped_session(other)
    try:
        log_activity(db, Action.TASK_CREATED, details={"whose": "mine"})
        log_activity(other_db, Action.TASK_CREATED, details={"whose": "theirs"})
        db.commit()
        other_db.commit()

        mine, _ = svc.list_activity(db)
        theirs, _ = svc.list_activity(other_db)
    finally:
        other_db.close()

    assert [r.details["whose"] for r in mine] == ["mine"]
    assert [r.details["whose"] for r in theirs] == ["theirs"]


def test_list_activity_on_an_unscoped_session_fails_loudly_instead_of_leaking():
    unscoped = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="owner_id"):
            svc.list_activity(unscoped)
    finally:
        unscoped.close()


# ---------------------------------------------------------------------------
# purge_older_than
# ---------------------------------------------------------------------------


def _backdate(row_id: int, days: int) -> None:
    with SessionLocal() as everyone:
        everyone.query(ActivityLog).filter(ActivityLog.id == row_id).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=days)}
        )
        everyone.commit()


def test_purge_deletes_only_rows_older_than_the_cutoff(db):
    old = log_activity(db, Action.TASK_CREATED, details={"age": "old"})
    fresh = log_activity(db, Action.TASK_CREATED, details={"age": "fresh"})
    db.commit()
    _backdate(old.id, 200)
    _backdate(fresh.id, 10)

    removed = svc.purge_older_than(db, 180)
    db.commit()

    assert removed == 1
    assert [r.details["age"] for r in _all_rows()] == ["fresh"]


def test_purge_with_zero_or_negative_days_keeps_everything(db):
    row = log_activity(db, Action.TASK_CREATED)
    db.commit()
    _backdate(row.id, 5000)

    assert svc.purge_older_than(db, 0) == 0
    assert svc.purge_older_than(db, -1) == 0
    assert len(_all_rows()) == 1


def test_purge_only_touches_the_scoped_users_rows(db):
    other = make_user("other@example.com")
    other_db = scoped_session(other)
    try:
        mine = log_activity(db, Action.TASK_CREATED)
        theirs = log_activity(other_db, Action.TASK_CREATED)
        db.commit()
        other_db.commit()
        _backdate(mine.id, 400)
        _backdate(theirs.id, 400)

        assert svc.purge_older_than(db, 180) == 1
        db.commit()
    finally:
        other_db.close()

    [remaining] = _all_rows()
    assert remaining.user_id == other.id
