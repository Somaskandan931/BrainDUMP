"""services/explanation_service.py and its four HTTP endpoints."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app.db.database import owner_id
from backend.app.ai import episodic_memory
from backend.app.models.dependency import Dependency
from backend.app.models.enums import EpisodicEventType, Importance
from backend.app.services.ai import explanation_service
from tests.helpers import make_completed_task, make_project, make_task, utcnow

COMPONENT_KEYS = {"deadline_risk", "importance", "estimated_hours", "context_switch_cost", "energy_fit"}


# --- Why this task? ----------------------------------------------------------


def test_next_task_explanation_is_none_when_nothing_is_active(db):
    assert explanation_service.explain_next_task(db) is None


def test_next_task_endpoint_returns_null_explanation_when_empty(client):
    response = client.get("/api/planner/next-task/explain")
    assert response.status_code == 200
    assert response.json() == {"explanation": None}


def test_next_task_explanation_matches_the_recommended_task(client, db):
    make_task(db, "low", importance=Importance.LOW, deadline_in_days=20, estimated_hours=2)
    urgent = make_task(db, "urgent", importance=Importance.CRITICAL, deadline_in_days=0.5, estimated_hours=2)

    recommended = client.get("/api/planner/next-task").json()["task"]
    explanation = client.get("/api/planner/next-task/explain").json()["explanation"]

    assert recommended["id"] == urgent.id == explanation["task_id"]
    assert set(explanation["components"]) == COMPONENT_KEYS
    assert any("deadline is" in r for r in explanation["reasons"])
    assert any("critical importance" in r for r in explanation["reasons"])


def test_deadline_reason_works_with_naive_datetimes_from_sqlite(client, db):
    """Regression: SQLite returns deadlines naive; subtracting them from an
    aware `now` raised TypeError and the endpoint 500'd on first real use."""
    make_task(db, "due soon", deadline_in_days=2, estimated_hours=1)
    response = client.get("/api/planner/next-task/explain")

    assert response.status_code == 200
    assert response.json()["explanation"] is not None


def test_overdue_task_is_called_out(client, db):
    make_task(db, "late", deadline_in_days=-1, estimated_hours=1)
    reasons = client.get("/api/planner/next-task/explain").json()["explanation"]["reasons"]
    assert "its deadline has already passed" in reasons


def test_explanation_counts_tasks_it_unblocks(client, db):
    blocker = make_task(db, "blocker", importance=Importance.CRITICAL, deadline_in_days=1, estimated_hours=1)
    waiting = make_task(db, "waiting", importance=Importance.LOW, estimated_hours=1)
    db.add(Dependency(user_id=owner_id(db), task_id=waiting.id, depends_on_task_id=blocker.id))
    db.commit()

    explanation = client.get("/api/planner/next-task/explain").json()["explanation"]

    assert explanation["task_id"] == blocker.id
    assert explanation["unlocks_task_count"] == 1
    assert any("unlocks 1 dependent" in r for r in explanation["reasons"])


# --- Why this estimate? ------------------------------------------------------


def test_estimate_explanation_for_a_task_with_no_history(client, db):
    task = make_task(db, importance=Importance.HIGH)
    body = client.get(f"/api/tasks/{task.id}/explain-estimate").json()

    assert body["base_tier"] == "default"
    assert body["calibration_bias_pct"] is None
    assert body["calibrated_hours"] == body["base_hours"]
    assert any("No personal calibration applied" in r for r in body["reasons"])


def test_estimate_explanation_reports_the_applied_calibration(client, db):
    from backend.app.ml.calibration import MIN_SAMPLES
    from tests.helpers import make_resolved_prediction

    project = make_project(db, "Research")
    for _ in range(4):
        make_completed_task(db, project=project, estimated_hours=2.0, actual_hours=2.0)
    anchor = make_task(db, "anchor")
    for _ in range(MIN_SAMPLES):
        make_resolved_prediction(db, anchor, str(project.id), predicted=2.0, actual=2.6)

    task = make_task(db, project=project)
    body = client.get(f"/api/tasks/{task.id}/explain-estimate").json()

    assert body["base_tier"] == "project_history"
    assert body["calibration_applied_pct"] == pytest.approx(30.0)
    assert body["calibrated_hours"] == pytest.approx(body["base_hours"] * 1.3, abs=0.01)
    assert any("underestimated by 30%" in r for r in body["reasons"])


def test_estimate_explanation_404s_for_a_missing_task(client):
    assert client.get("/api/tasks/9999/explain-estimate").status_code == 404


# --- Why is this deadline at risk? ------------------------------------------


def test_deadline_risk_explanation_requires_a_deadline(client, db):
    task = make_task(db, "no deadline")
    response = client.get(f"/api/tasks/{task.id}/explain-deadline-risk")
    assert response.status_code == 400


def test_deadline_risk_explanation_includes_the_buffer_plan(client, db):
    task = make_task(db, "report", deadline_in_days=4, estimated_hours=3)
    body = client.get(f"/api/tasks/{task.id}/explain-deadline-risk").json()

    assert body["task_id"] == task.id
    assert {b["level"] for b in body["plan"]["buffers"]} == {"aggressive", "default", "safe"}
    assert any("of estimated work remains" in r for r in body["reasons"])


def test_deadline_risk_survives_a_risk_score_without_a_probability(client, db):
    """Regression: formatting a None completion_probability raised TypeError."""
    task = make_task(db, "half-scored", deadline_in_days=4, estimated_hours=3, risk_score=0.4)
    response = client.get(f"/api/tasks/{task.id}/explain-deadline-risk")

    assert response.status_code == 200
    reasons = response.json()["reasons"]
    assert any("Current risk score: 0.40." in r for r in reasons)


def test_deadline_risk_reports_impossible_deadlines(client, db):
    task = make_task(db, "hopeless", deadline_in_days=0.2, estimated_hours=40)
    reasons = client.get(f"/api/tasks/{task.id}/explain-deadline-risk").json()["reasons"]
    assert any("isn't enough free calendar time" in r for r in reasons)


# --- Why did my schedule change? --------------------------------------------


def test_schedule_change_is_none_before_any_replan(db):
    assert explanation_service.explain_schedule_change(db) is None


def test_schedule_change_endpoint_null_before_any_replan(client):
    assert client.get("/api/planner/replan/explain").json() == {"explanation": None}


def test_schedule_change_explains_the_latest_replan(client, db):
    make_task(db, "a", deadline_in_days=3, estimated_hours=2)
    make_task(db, "b", deadline_in_days=5, estimated_hours=1)

    assert client.post("/api/planner/replan").status_code == 200
    explanation = client.get("/api/planner/replan/explain").json()["explanation"]

    assert explanation["summary"].startswith("Replan")
    assert explanation["occurred_on"] == utcnow().date().isoformat()
    assert any("No task is at risk" in r or "still at risk" in r for r in explanation["reasons"])


def test_schedule_change_calls_out_a_recent_overrun(client, db):
    overrun = make_completed_task(db, "Big report", estimated_hours=2.0, actual_hours=3.0, completed_days_ago=0.1)
    make_task(db, "next", deadline_in_days=3, estimated_hours=1)
    client.post("/api/planner/replan")

    reasons = client.get("/api/planner/replan/explain").json()["explanation"]["reasons"]
    assert any(overrun.title in r and "+50%" in r for r in reasons)


def test_schedule_change_uses_the_most_recent_replan_event(db):
    pushed = make_task(db, "Tidy inbox", importance=Importance.LOW, deadline_in_days=9, estimated_hours=1)
    today = utcnow().date()

    episodic_memory.record_event(
        db,
        EpisodicEventType.PLANNING_DECISION,
        title="Replan: older",
        summary="Replan: repacked 1 task(s).",
        occurred_on=today - timedelta(days=3),
        payload={"rescheduled_task_ids": [pushed.id]},
    )
    episodic_memory.record_event(
        db,
        EpisodicEventType.PLANNING_DECISION,
        title="Replan: newer",
        summary="Replan: pushed out 1 lower-priority task(s).",
        occurred_on=today,
        payload={"demoted_task_ids": [pushed.id]},
    )

    explanation = explanation_service.explain_schedule_change(db)

    assert explanation["summary"] == "Replan: pushed out 1 lower-priority task(s)."
    assert explanation["occurred_on"] == today.isoformat()
    assert any("pushed out to protect higher-priority" in r and "Tidy inbox" in r for r in explanation["reasons"])
    assert not any("repacked" in r for r in explanation["reasons"])
