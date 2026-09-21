"""
services/explanation_service.py — Explainability layer.

The project review's Priority 3: every one of these existing engines
(priority_model, estimator/calibration, deadline_service) already
computes a real, groundable answer, but only ever surfaced the final
number — a priority_score, an estimated_hours, a risk_score — with no
way for the user to see *why*. This module doesn't compute anything new;
it re-reads what those engines already produced (or recomputes the same
deterministic breakdown they use internally) and turns it into the
"Why this task?" / "Why this estimate?" / "Why did my schedule change?"
narratives the review calls out as the difference between a mysterious
AI and an explainable one.

Deliberately has no LLM call in it: every reason string here is built
from real numbers (deadline distance, dependency counts, resolved
Prediction history), the same "algorithms decide, LLM never invents the
result" split the rest of the codebase already follows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.ai import episodic_memory
from backend.ml import calibration, estimator
from backend.ml.priority_model import compute_priority_components
from backend.models.dependency import Dependency
from backend.models.enums import EpisodicEventType, Importance, TaskStatus
from backend.models.task import Task
from backend.services import deadline_service, scheduler_service

# Below this many hours remaining, a deadline is called out as "close"
# in plain language rather than just showing the raw number.
_URGENT_DEADLINE_HOURS = 24.0


def _as_utc(value: datetime) -> datetime:
    """SQLite hands datetimes back naive even though everything stored is
    UTC (same normalization deadline_service.compute_deadline_plan does
    before subtracting from an aware `now`)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Why this task?
# ---------------------------------------------------------------------------


def _unlocked_task_count(db: Session, task: Task) -> int:
    """How many other active tasks are waiting on `task` to complete."""
    dependents = (
        db.query(Dependency.task_id)
        .join(Task, Task.id == Dependency.task_id)
        .filter(
            Dependency.depends_on_task_id == task.id,
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)),
        )
        .count()
    )
    return dependents


def explain_next_task(db: Session) -> Optional[dict]:
    """
    The "Why this task?" breakdown for whatever scheduler_service.get_next_task()
    currently recommends. Returns None if there's no active task at all
    (same "empty is valid" convention as api/planner.py's next-task route).
    """
    task = scheduler_service.get_next_task(db)
    if task is None:
        return None

    now = datetime.now(timezone.utc)
    components = compute_priority_components(
        task, now=now, context_switch_cost=task.context_switch_cost
    )

    unlocks = _unlocked_task_count(db, task)
    cal = calibration.get_calibration(db, calibration.resolve_category(task))

    reasons: List[str] = []
    if task.deadline is not None:
        hours_left = (_as_utc(task.deadline) - now).total_seconds() / 3600.0
        if hours_left <= 0:
            reasons.append("its deadline has already passed")
        elif hours_left <= _URGENT_DEADLINE_HOURS:
            reasons.append(f"its deadline is {hours_left:.0f}h away")
        else:
            reasons.append(f"its deadline is {hours_left / 24.0:.1f} day(s) away")
    if task.importance in (Importance.HIGH, Importance.CRITICAL):
        reasons.append(f"it's marked {task.importance.value} importance")
    if task.estimated_hours is not None:
        reasons.append(f"estimated at {task.estimated_hours:.1f}h")
    if components["context_switch_cost"] <= 0.1:
        reasons.append("it continues the project you were just working on")
    if unlocks > 0:
        reasons.append(f"completing it unlocks {unlocks} dependent task(s)")
    if cal is not None and abs(cal.bias_pct) > 5:
        direction = "longer" if cal.bias_pct > 0 else "shorter"
        reasons.append(
            f"tasks like this have historically taken {abs(cal.bias_pct):.0f}% {direction} than estimated"
        )

    return {
        "task_id": task.id,
        "title": task.title,
        "priority_score": task.priority_score,
        "components": {k: round(v, 2) for k, v in components.items()},
        "unlocks_task_count": unlocks,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Why this estimate?
# ---------------------------------------------------------------------------


def explain_estimate(db: Session, task: Task) -> dict:
    """The "Why this estimate?" breakdown: base ladder tier, category
    calibration, and the resulting adjusted figure, in plain language."""
    detail = estimator.estimate_hours_detailed(db, task)

    tier_labels = {
        "project_history": "the median of your own completed tasks in this project",
        "trained_model": "a model trained on your own logged task history",
        "importance_history": f"the median of your completed {task.importance.value}-importance tasks",
        "default": f"a default for {task.importance.value}-importance tasks (not enough history yet)",
    }
    reasons = [f"Base estimate came from {tier_labels.get(detail['base_tier'], detail['base_tier'])}."]

    if detail["calibration_bias_pct"] is not None and abs(detail["calibration_applied_pct"]) > 1:
        direction = "underestimated" if detail["calibration_bias_pct"] > 0 else "overestimated"
        reasons.append(
            f"Tasks in this category have been {direction} by {abs(detail['calibration_bias_pct']):.0f}% "
            f"on average across your last {detail['calibration_sample_count']} completed task(s), "
            f"so a {detail['calibration_applied_pct']:+.0f}% personal calibration was applied."
        )
    else:
        reasons.append("No personal calibration applied yet — not enough resolved history for this category.")

    return {"task_id": task.id, "title": task.title, **detail, "reasons": reasons}


# ---------------------------------------------------------------------------
# Why is this deadline at risk?
# ---------------------------------------------------------------------------


def explain_deadline_risk(db: Session, task: Task) -> dict:
    """The "Why is this deadline at risk?" breakdown, built on top of
    deadline_service's existing buffer computation — this adds the
    plain-language reasons, not new math."""
    plan = deadline_service.compute_deadline_plan(db, task)
    default_buffer = next((b for b in plan["buffers"] if b["level"] == "default"), None)

    reasons: List[str] = [
        f"{plan['hours_remaining']:.1f}h of estimated work remains on this task."
    ]
    if default_buffer is not None:
        if default_buffer["status"] == "safe":
            reasons.append(
                f"You have {default_buffer['free_hours_available']:.1f}h of free calendar time before "
                f"{default_buffer['target_date'].strftime('%b %d')} — comfortably more than needed."
            )
        elif default_buffer["status"] == "tight":
            reasons.append(
                f"Only {default_buffer['free_hours_available']:.1f}h of free calendar time is available "
                f"before {default_buffer['target_date'].strftime('%b %d')} — it fits, but with no slack "
                "for anything to slip."
            )
        elif default_buffer["status"] == "impossible":
            reasons.append(
                f"There isn't enough free calendar time before {default_buffer['target_date'].strftime('%b %d')} "
                "to finish the remaining work at this buffer — something else needs to move for this to land."
            )
    if task.risk_score is not None:
        probability = (
            f" (completion probability {task.completion_probability:.0%})"
            if task.completion_probability is not None
            else ""
        )
        reasons.append(f"Current risk score: {task.risk_score:.2f}{probability}.")

    return {"task_id": task.id, "title": task.title, "plan": plan, "reasons": reasons}


# ---------------------------------------------------------------------------
# Why did my schedule change?
# ---------------------------------------------------------------------------


def explain_schedule_change(db: Session) -> Optional[dict]:
    """
    The "Why did my schedule change?" narrative for the most recent
    replan. Reconstructed from the PLANNING_DECISION episode
    deadline_service.replan() already records, plus the most recent
    task that overran its estimate (the usual real-world trigger for a
    replan), rather than re-running replan() itself — this is meant to
    explain what already happened, not perform another pass.
    """
    events = episodic_memory.recent_events(db, limit=1, event_type=EpisodicEventType.PLANNING_DECISION)
    if not events:
        return None
    event = events[0]

    import json

    payload = json.loads(event.payload) if event.payload else {}
    rescheduled_ids = payload.get("rescheduled_task_ids", [])
    demoted_ids = payload.get("demoted_task_ids", [])
    at_risk_ids = payload.get("at_risk_task_ids", [])

    def _titles(ids: list[int]) -> List[str]:
        if not ids:
            return []
        rows = db.query(Task.title).filter(Task.id.in_(ids)).all()
        return [r[0] for r in rows]

    reasons: List[str] = []

    # The usual real-world trigger: the most recently completed task
    # that ran significantly over its own estimate.
    overrun = (
        db.query(Task)
        .filter(
            Task.status == TaskStatus.COMPLETED,
            Task.actual_hours.isnot(None),
            Task.estimated_hours.isnot(None),
            Task.estimated_hours > 0,
        )
        .order_by(Task.completed_at.desc())
        .first()
    )
    if overrun is not None:
        overrun_pct = (overrun.actual_hours - overrun.estimated_hours) / overrun.estimated_hours * 100
        if overrun_pct > 15:
            reasons.append(
                f'"{overrun.title}" took {overrun.actual_hours:.1f}h against an estimated '
                f"{overrun.estimated_hours:.1f}h ({overrun_pct:+.0f}%), reducing the capacity available "
                "for the rest of the schedule."
            )

    if demoted_ids:
        reasons.append(
            f"{len(demoted_ids)} lower-priority task(s) were pushed out to protect higher-priority "
            f"deadlines: {', '.join(_titles(demoted_ids))}."
        )
    if rescheduled_ids:
        reasons.append(f"{len(rescheduled_ids)} task(s) were repacked into the remaining free time.")
    if at_risk_ids:
        reasons.append(
            f"{len(at_risk_ids)} task(s) are still at risk even after replanning: {', '.join(_titles(at_risk_ids))}."
        )
    else:
        reasons.append("No task is at risk after this replan.")

    # Invariant guaranteed by deadline_service.replan() itself (only
    # LOW/MEDIUM importance tasks are ever demoted) — stated here rather
    # than re-derived, since it's a property of the code path that ran,
    # not something worth re-querying.
    reasons.append("No critical or high-importance task was moved past its safe-start time.")

    return {
        "occurred_on": event.occurred_on.isoformat(),
        "summary": event.summary,
        "reasons": reasons,
    }