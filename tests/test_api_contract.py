"""
Response-shape contract for the endpoints the frontend consumes.

frontend/services/types.ts hand-mirrors these payloads (there's no codegen
step), so a backend rename that would silently break a React panel fails
here instead. When a key below changes, update types.ts in the same commit.
"""

from __future__ import annotations

from tests.helpers import make_task


def _seed_and_get_task_id(client) -> int:
    client.post("/api/demo/seed")
    return client.get("/api/planner/next-task/explain").json()["explanation"]["task_id"]


def test_next_task_explanation_shape(client):
    _seed_and_get_task_id(client)
    explanation = client.get("/api/planner/next-task/explain").json()["explanation"]

    # NextTaskExplanation
    assert set(explanation) == {
        "task_id", "title", "priority_score", "components", "unlocks_task_count", "reasons",
    }
    # PriorityComponents
    assert set(explanation["components"]) == {
        "deadline_risk", "importance", "estimated_hours", "context_switch_cost", "energy_fit",
    }
    assert isinstance(explanation["reasons"], list) and all(isinstance(r, str) for r in explanation["reasons"])


def test_estimate_explanation_shape(client):
    task_id = _seed_and_get_task_id(client)
    body = client.get(f"/api/tasks/{task_id}/explain-estimate").json()

    # EstimateExplanation
    assert set(body) == {
        "task_id", "title", "base_hours", "base_tier", "confidence", "category",
        "calibration_bias_pct", "calibration_sample_count", "calibration_applied_pct",
        "calibrated_hours", "reasons",
    }
    assert body["base_tier"] in {"project_history", "trained_model", "importance_history", "default"}


def test_deadline_risk_explanation_shape(client):
    task_id = _seed_and_get_task_id(client)
    body = client.get(f"/api/tasks/{task_id}/explain-deadline-risk").json()

    # DeadlineRiskExplanation embeds a TaskDeadlinePlan
    assert set(body) == {"task_id", "title", "plan", "reasons"}
    assert {"task_id", "title", "deadline", "estimated_hours", "hours_remaining", "buffers"} <= set(body["plan"])
    assert {
        "level", "target_date", "days_remaining", "free_hours_available",
        "hours_needed", "suggested_daily_hours", "status", "message",
    } <= set(body["plan"]["buffers"][0])


def test_schedule_change_explanation_shape(client):
    _seed_and_get_task_id(client)
    client.post("/api/planner/replan")
    explanation = client.get("/api/planner/replan/explain").json()["explanation"]

    # ScheduleChangeExplanation
    assert set(explanation) == {"occurred_on", "summary", "reasons"}


def test_calibration_shape(client):
    client.post("/api/demo/seed")
    body = client.get("/api/analytics/calibration").json()

    # CalibrationResponse / CalibrationCategory
    assert set(body) == {"categories"}
    assert set(body["categories"][0]) == {"category", "bias_pct", "sample_count", "confidence"}


def test_calibration_is_sorted_by_largest_bias_first(client):
    client.post("/api/demo/seed")
    biases = [abs(c["bias_pct"]) for c in client.get("/api/analytics/calibration").json()["categories"]]
    assert biases == sorted(biases, reverse=True)


def test_demo_response_shapes(client):
    seed = client.post("/api/demo/seed").json()
    # DemoSeedResponse
    assert set(seed) == {
        "projects_created", "tasks_completed", "tasks_pending", "sessions_created",
        "predictions_created", "metrics_days", "already_seeded",
    }
    # DemoResetResponse
    assert set(client.post("/api/demo/reset").json()) == {"projects_removed", "metrics_removed"}


def test_explain_estimate_for_a_task_with_only_an_estimate_and_no_deadline(client, db):
    """TaskRow now offers 'Why this estimate?' on rows with no deadline."""
    task = make_task(db, "no deadline", estimated_hours=2.0)
    assert client.get(f"/api/tasks/{task.id}/explain-estimate").status_code == 200
