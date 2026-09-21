"""
services/execution_score_service.py — The Execution Score (PRD §15, §37,
Algorithm 8 ⭐⭐⭐⭐⭐).

PRD §15 calls this out as the one feature that most differentiates
BrainDUMP: a single 0-100 number, shown as the dashboard hero, answering
"is today's plan actually realistic?" instead of making the user infer
that from a task list. Despite being starred as a core algorithm, it
did not exist anywhere in the codebase before this — no service, no
schema, no route, no frontend component.

The PRD's formula (Algorithm 8) lists seven qualitative ingredients
(Capacity, Deadline Safety, Buffer, Focus Quality, Workload Balance,
Calendar Stability, Completion Confidence) but — unlike the Priority
Score in §21, which ships exact weights — gives no numbers or precise
definitions to implement directly. Rather than invent input signals
the app doesn't actually track, this implementation grounds every
component in a number some other service already computes for real:

  Capacity              -> workload_service (today's utilization_pct)
  Deadline Safety        -> deadline_service (completion_probability on
                             tasks due soon)
  Buffer                 -> workload_service (today's free hours vs.
                             hours actually due today)
  Workload Balance       -> workload_service (variance in utilization
                             across the coming week — a spiky week is
                             less stable than an even one)
  Calendar Stability      -> deadline_service.detect_at_risk_tasks (share
                             of active tasks that are NOT at risk)
  Completion Confidence   -> analytics_service.estimation_error (how
                             close recent estimates have run to actual
                             time; a large bias erodes trust in the plan)

"Focus Quality" is deliberately NOT included as its own component: the
PRD describes it as measuring interruptions/session quality, and the
only real signal available (WorkSession predicted vs. actual duration)
is already the Completion Confidence input above — adding it twice
would double-count the same data under two names rather than add a new
one. Weights below are this module's own design (not from the PRD,
which gives none) and are named constants so they're easy to retune.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from statistics import pstdev
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.enums import TaskStatus
from backend.models.metrics import ProductivityMetric
from backend.models.task import Task
from backend.services import analytics_service, deadline_service, workload_service

# Component weights — must sum to 1.0.
_WEIGHT_CAPACITY = 0.25
_WEIGHT_DEADLINE_SAFETY = 0.25
_WEIGHT_BUFFER = 0.15
_WEIGHT_WORKLOAD_BALANCE = 0.10
_WEIGHT_CALENDAR_STABILITY = 0.15
_WEIGHT_COMPLETION_CONFIDENCE = 0.10

# How far ahead a deadline counts toward "Deadline Safety" — matches the
# frontend's own "urgent" window (lib/format.ts formatDeadline: days <= 2).
_DEADLINE_SAFETY_LOOKAHEAD_DAYS = 2


@dataclass
class ScoreComponent:
    name: str
    score: float  # 0-100
    weight: float
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class ExecutionScore:
    score: int  # 0-100, rounded for display
    band: str  # "excellent" | "healthy" | "busy" | "high_risk" | "impossible"
    headline: str
    components: List[ScoreComponent]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "band": self.band,
            "headline": self.headline,
            "components": [c.to_dict() for c in self.components],
        }


def _band_for(score: int) -> tuple[str, str]:
    """Maps to the PRD §15/§Algorithm-8 meaning table (100/80/60/40/20)."""
    if score >= 85:
        return "excellent", "Today's plan is realistic, with healthy margin."
    if score >= 65:
        return "healthy", "Today's plan is on track."
    if score >= 45:
        return "busy", "Today is busy — little room for surprises."
    if score >= 25:
        return "high_risk", "Today's workload exceeds comfortable capacity."
    return "impossible", "Today's plan isn't achievable as scheduled."


def _capacity_component(today_utilization_pct: float) -> ScoreComponent:
    """PRD §22 capacity zones: 0-70 green, 70-90 yellow, 90-100 orange, 100+ red."""
    u = today_utilization_pct
    if u <= 70:
        score = 100.0
    elif u <= 90:
        score = 100.0 - (u - 70) * (40.0 / 20.0)  # 100 -> 60
    elif u <= 100:
        score = 60.0 - (u - 90) * (30.0 / 10.0)  # 60 -> 30
    else:
        score = max(0.0, 30.0 - (u - 100) * 0.5)
    return ScoreComponent(
        "capacity", score, _WEIGHT_CAPACITY, f"Today's schedule is {u:.0f}% utilized."
    )


def _deadline_safety_component(db: Session, now: datetime) -> ScoreComponent:
    horizon = now + timedelta(days=_DEADLINE_SAFETY_LOOKAHEAD_DAYS)
    soon = (
        db.query(Task)
        .filter(
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)),
            Task.deadline.isnot(None),
            Task.deadline <= horizon,
        )
        .all()
    )
    if not soon:
        return ScoreComponent(
            "deadline_safety", 100.0, _WEIGHT_DEADLINE_SAFETY, "Nothing due in the next 2 days."
        )
    probs = [
        t.completion_probability if t.completion_probability is not None else (1.0 - (t.risk_score or 0.5))
        for t in soon
    ]
    avg = sum(probs) / len(probs)
    return ScoreComponent(
        "deadline_safety",
        avg * 100,
        _WEIGHT_DEADLINE_SAFETY,
        f"{len(soon)} task{'s' if len(soon) != 1 else ''} due within 2 days, "
        f"{avg * 100:.0f}% average completion probability.",
    )


def _buffer_component(today) -> ScoreComponent:
    """today is a WorkloadDay from workload_service — free hours vs. capacity."""
    free_hours = max(0.0, today.capacity_hours - today.allocated_hours)
    if today.capacity_hours <= 0:
        score = 100.0
    else:
        score = min(100.0, (free_hours / today.capacity_hours) * 100 * 2.5)  # a quarter free -> ~62
    return ScoreComponent(
        "buffer", score, _WEIGHT_BUFFER, f"{free_hours:.1f}h free out of {today.capacity_hours:.0f}h today."
    )


def _workload_balance_component(days) -> ScoreComponent:
    utilizations = [d.utilization_pct for d in days]
    if len(utilizations) < 2:
        return ScoreComponent(
            "workload_balance", 100.0, _WEIGHT_WORKLOAD_BALANCE, "Not enough of the week scheduled yet to judge balance."
        )
    spread = pstdev(utilizations)
    score = max(0.0, 100.0 - spread)
    return ScoreComponent(
        "workload_balance",
        score,
        _WEIGHT_WORKLOAD_BALANCE,
        f"Workload varies by ~{spread:.0f} points across the coming week.",
    )


def _calendar_stability_component(db: Session, now: datetime) -> ScoreComponent:
    active = (
        db.query(Task)
        .filter(Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)))
        .count()
    )
    if active == 0:
        return ScoreComponent(
            "calendar_stability", 100.0, _WEIGHT_CALENDAR_STABILITY, "No active tasks to destabilize the plan."
        )
    at_risk = len(deadline_service.detect_at_risk_tasks(db, now))
    score = max(0.0, 100.0 * (1 - at_risk / active))
    return ScoreComponent(
        "calendar_stability",
        score,
        _WEIGHT_CALENDAR_STABILITY,
        f"{at_risk} of {active} active task{'s' if active != 1 else ''} at risk of missing its deadline.",
    )


def _completion_confidence_component(db: Session) -> ScoreComponent:
    result = analytics_service.estimation_error(db)
    if result.overall_average_error_pct is None:
        return ScoreComponent(
            "completion_confidence",
            75.0,
            _WEIGHT_COMPLETION_CONFIDENCE,
            "Not enough completed tasks yet to judge estimation accuracy.",
        )
    error = abs(result.overall_average_error_pct)
    score = max(0.0, 100.0 - error)
    return ScoreComponent(
        "completion_confidence",
        score,
        _WEIGHT_COMPLETION_CONFIDENCE,
        f"Estimates have run {result.overall_average_error_pct:+.0f}% off actual time recently.",
    )


def compute_execution_score(db: Session, now: Optional[datetime] = None) -> ExecutionScore:
    now = now or datetime.now(timezone.utc)

    workload = workload_service.get_workload(db, now=now, days=7)
    today = workload.days[0] if workload.days else None

    components = [
        _capacity_component(today.utilization_pct if today else 0.0),
        _deadline_safety_component(db, now),
        _buffer_component(today) if today else ScoreComponent(
            "buffer", 100.0, _WEIGHT_BUFFER, "No scheduling data for today yet."
        ),
        _workload_balance_component(workload.days),
        _calendar_stability_component(db, now),
        _completion_confidence_component(db),
    ]

    total = sum(c.score * c.weight for c in components)
    score = round(max(0.0, min(100.0, total)))
    band, headline = _band_for(score)

    return ExecutionScore(score=score, band=band, headline=headline, components=components)


@dataclass
class ExecutionScoreTrendPoint:
    date: date_type
    score: int
    band: str

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "score": self.score, "band": self.band}


def get_execution_score_trend(db: Session, days: int = 14, now: Optional[datetime] = None) -> List[ExecutionScoreTrendPoint]:
    """
    Historical Execution Score, one point per day, for the analytics-page
    trend view ("your score this week") flagged as the natural follow-up
    once the score itself existed.

    Backed by ProductivityMetric.execution_score, which the nightly job
    (scheduler/nightly.py) snapshots once per day -- the same
    pre-aggregated-rollup pattern the rest of analytics_service already
    uses, rather than recomputing every historical day's score live on
    every request (today's components depend on the *current* schedule
    state, so a "historical" live recompute wouldn't actually reflect
    what the plan looked like on that day anyway).

    Today's own point is filled in live if the nightly job hasn't run
    yet today (there's no ProductivityMetric row, or its score is still
    null), so the trend line doesn't have a visible gap at the most
    recent, most-looked-at day.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()
    start = today - timedelta(days=days - 1)

    rows = {
        m.date: m
        for m in db.query(ProductivityMetric)
        .filter(ProductivityMetric.date >= start, ProductivityMetric.date <= today)
        .all()
    }

    points: List[ExecutionScoreTrendPoint] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = rows.get(day)
        if row is not None and row.execution_score is not None:
            score = row.execution_score
        elif day == today:
            score = compute_execution_score(db, now=now).score
        else:
            continue  # no snapshot for a past day -- skip rather than fabricate a number
        band, _ = _band_for(score)
        points.append(ExecutionScoreTrendPoint(date=day, score=score, band=band))

    return points
