"""
ml/calibration.py — Personal estimation calibration.

Closes the loop the project review called out as BrainDUMP's biggest
potential differentiator: services/analytics_service.estimation_error()
already computes a *signed* per-category bias ("Research tasks:
consistently +34% underestimated") from resolved Predictions, but
nothing fed that number back into the next estimate. This module is
that feedback path:

    generic estimate (ml/estimator.py's existing ladder)
            -> personal bias for this task's category
            -> calibrated estimate

Deliberately a small, explainable adjustment rather than a second
model: a signed average percentage error nudges the base estimate up
or down. Two guards keep it from misbehaving:

- MIN_SAMPLES: below this many resolved predictions in the category,
  the bias is too noisy to act on (same reasoning as ml/estimator.py's
  own _CONFIDENT_SAMPLE_SIZE gate on the base estimate).
- MAX_ADJUSTMENT_PCT: the applied adjustment is clamped even once
  there's plenty of history, since a task that's ever taken 5x longer
  than predicted usually means the estimate itself was wrong for a
  different reason (missing scope, a blocked dependency), not that a
  400% multiplier is the right fix for every future task in that
  category.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.prediction import Prediction
from backend.models.task import Task

MIN_SAMPLES = 3
MAX_ADJUSTMENT_PCT = 60.0

# Only resolved predictions from within this window count towards the
# bias -- old history from a category the user has since gotten better
# (or worse) at estimating shouldn't keep pulling new estimates forever.
LOOKBACK_DAYS = 90


@dataclass
class Calibration:
    category: str
    bias_pct: float  # signed: +N% = the user underestimates (actual ran longer than predicted)
    sample_count: int
    confidence: float  # 0-1, scales with sample_count


def resolve_category(task: Task) -> str:
    """Same grouping key ml/estimator.py's ensure_estimate() already logs
    Predictions under: the project id if the task belongs to one,
    otherwise its importance tier. Keeping this identical to the
    logging key is what lets get_calibration() actually find history
    for a task's category."""
    return str(task.project_id) if task.project_id is not None else task.importance.value


def get_calibration(db: Session, category: str, *, now: Optional[datetime] = None) -> Optional[Calibration]:
    """
    The signed average error_pct for `category`'s resolved Predictions
    in the last LOOKBACK_DAYS, or None if there isn't enough history to
    trust yet. error_pct is (actual - predicted) / predicted * 100, so
    positive means predictions in this category have been running short.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)

    rows = (
        db.query(Prediction.error_pct)
        .filter(
            Prediction.category == category,
            Prediction.error_pct.isnot(None),
            Prediction.resolved_at.isnot(None),
            Prediction.resolved_at >= since,
        )
        .all()
    )
    errors = [r[0] for r in rows if r[0] is not None]
    if len(errors) < MIN_SAMPLES:
        return None

    bias = sum(errors) / len(errors)
    confidence = min(1.0, len(errors) / 10.0)
    return Calibration(
        category=category,
        bias_pct=round(bias, 2),
        sample_count=len(errors),
        confidence=round(confidence, 2),
    )


def apply_calibration(base_hours: float, calibration: Optional[Calibration]) -> tuple[float, float]:
    """
    Returns (calibrated_hours, applied_pct). applied_pct is the clamped
    figure actually used, kept separate from calibration.bias_pct so a
    caller/explanation can show both "your true historical bias" and
    "what was applied" on the rare occasion the clamp kicks in.
    """
    if calibration is None or base_hours <= 0:
        return round(base_hours, 2), 0.0
    applied_pct = max(-MAX_ADJUSTMENT_PCT, min(MAX_ADJUSTMENT_PCT, calibration.bias_pct))
    calibrated = base_hours * (1 + applied_pct / 100.0)
    return round(max(0.1, calibrated), 2), applied_pct