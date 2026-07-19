"""
ml/priority_model.py — Computes the composite priority score.

Priority Score = Deadline Risk + Importance + Estimated Hours
                 + Context Switching Cost + Energy Pattern Fit

Milestone 5: hand-tuned weighted sum (weights in backend/config.py), each
component normalized to roughly 0-1 before weighting so priority_score
itself lands in a stable, comparable 0-1 range across tasks.

Milestone 8: replace this with a learned model once enough labeled "what
the user actually worked on" data exists (Prediction.predicted_priority_score
already logs every score this module produces, so that training set is
being built starting now).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend import config
from backend.models.enums import Importance
from backend.models.task import Task

_IMPORTANCE_SCORE = {
    Importance.LOW: 0.2,
    Importance.MEDIUM: 0.5,
    Importance.HIGH: 0.8,
    Importance.CRITICAL: 1.0,
}

# Deadline risk saturates: nothing due for weeks scores near 0, anything
# overdue or due within a few hours scores 1.0. Risk climbs the closer
# (or more overdue) the deadline is, using this many days as the horizon
# over which risk ramps from 0 to 1.
_DEADLINE_RISK_HORIZON_DAYS = 10.0

# Longer tasks are (slightly) deprioritized relative to quick wins, since
# clearing small tasks reduces total open-task count and context-switch
# overhead. Capped so a single huge task doesn't get buried indefinitely.
_LONG_TASK_HOURS_CAP = 8.0


def _deadline_risk(task: Task, now: datetime) -> float:
    if task.deadline is None:
        return 0.15  # no deadline: low-but-nonzero baseline risk, not "never"

    deadline = task.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    days_remaining = (deadline - now).total_seconds() / 86400.0
    if days_remaining <= 0:
        return 1.0  # overdue — maximum risk

    risk = 1.0 - (days_remaining / _DEADLINE_RISK_HORIZON_DAYS)
    return max(0.0, min(1.0, risk))


def _importance_score(task: Task) -> float:
    return _IMPORTANCE_SCORE.get(task.importance, 0.5)


def _estimated_hours_score(task: Task) -> float:
    """Shorter tasks score slightly higher (quick wins first, all else equal)."""
    hours = task.estimated_hours if task.estimated_hours is not None else config.DEFAULT_TASK_HOURS
    hours = max(0.0, min(hours, _LONG_TASK_HOURS_CAP))
    return 1.0 - (hours / _LONG_TASK_HOURS_CAP)


def compute_context_switch_cost(task: Task, previous_task: Optional[Task]) -> float:
    """
    Cost of tackling `task` right after `previous_task` (the most recently
    worked-on or most recently scheduled task). Same project -> ~free;
    different project -> full penalty; no project on either side ->
    partial penalty, since one-off tasks don't carry real switching cost
    but aren't quite "continuing the same work" either.
    """
    if previous_task is None:
        return config.CONTEXT_SWITCH_NO_PROJECT_COST

    if task.project_id is None or previous_task.project_id is None:
        return config.CONTEXT_SWITCH_NO_PROJECT_COST

    if task.project_id == previous_task.project_id:
        return config.CONTEXT_SWITCH_SAME_PROJECT_COST

    return config.CONTEXT_SWITCH_DIFFERENT_PROJECT_COST


def _energy_fit(task: Task, at_hour: int, energy_pattern: dict[int, str]) -> float:
    """
    How well a task's energy_requirement matches the energy the user
    typically has at `at_hour`. No requirement set -> neutral fit (any
    time works), since we shouldn't penalize tasks the user didn't tag.
    """
    if task.energy_requirement is None:
        return 0.6

    user_energy = energy_pattern.get(at_hour, "medium")
    required = task.energy_requirement.value

    if required == user_energy:
        return 1.0

    tiers = ["low", "medium", "high"]
    try:
        distance = abs(tiers.index(required) - tiers.index(user_energy))
    except ValueError:
        return 0.5
    # Adjacent tiers (e.g. required=high, user=medium) still work reasonably;
    # opposite ends (required=high, user=low) fit poorly.
    return {0: 1.0, 1: 0.5, 2: 0.15}[distance]


def compute_priority_score(
    task: Task,
    *,
    now: Optional[datetime] = None,
    previous_task: Optional[Task] = None,
    at_hour: Optional[int] = None,
    energy_pattern: Optional[dict[int, str]] = None,
    context_switch_cost: Optional[float] = None,
) -> float:
    """
    Compute the composite priority_score (0-1, higher = do sooner) for a
    single task. `context_switch_cost`, if the caller already computed it
    (e.g. while walking a sorted schedule), is used as-is instead of being
    recomputed from `previous_task`.
    """
    now = now or datetime.now(timezone.utc)
    at_hour = at_hour if at_hour is not None else now.hour
    energy_pattern = energy_pattern or config.DEFAULT_ENERGY_PATTERN

    if context_switch_cost is None:
        context_switch_cost = compute_context_switch_cost(task, previous_task)

    weights = config.PRIORITY_WEIGHTS
    score = (
        weights["deadline_risk"] * _deadline_risk(task, now)
        + weights["importance"] * _importance_score(task)
        + weights["estimated_hours"] * _estimated_hours_score(task)
        + weights["context_switch_cost"] * context_switch_cost
        + weights["energy_fit"] * _energy_fit(task, at_hour, energy_pattern)
    )
    return round(max(0.0, min(1.0, score)), 4)


def compute_task_context_switch_field(task: Task, previous_task: Optional[Task]) -> float:
    """Thin wrapper so callers writing to Task.context_switch_cost don't import two names."""
    return compute_context_switch_cost(task, previous_task)
