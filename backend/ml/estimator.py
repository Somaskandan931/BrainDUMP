"""
ml/estimator.py — Predicts task duration from historical data.

Milestone 5: a statistical estimator — median actual_hours of the user's
own completed tasks, grouped first by project, falling back to importance
tier, falling back to a flat default — with a confidence_score derived
from how much matching history exists. Every prediction is logged to
Prediction so ml/trainer.py has (predicted, actual) pairs to work with.

Milestone 8: adds a third rung, between the two group-median tiers —
a RandomForestRegressor trained by ml/trainer.py on resolved Prediction
history (backend.ml.trainer.train_estimator(), run weekly from
scheduler/nightly.py). It's tried after the project-specific median
(that's still the single best signal when it exists — real history for
*this exact project*) and before the flat importance-only default, since
the trained model's coarse features (importance/energy/has_project/
has_deadline — no project id) make it a smarter fallback for "no
same-project history yet" than the crude same-importance-any-project
median, once enough training data exists. The model is loaded lazily and
optionally: no persisted MODELS_DIR/estimator.pkl (fresh install, or
ml/trainer.py hasn't hit its minimum sample threshold yet) just skips
this rung entirely, same as any other tier with nothing to offer.
"""

from __future__ import annotations

import logging
import statistics
from typing import List, Optional

from sqlalchemy.orm import Session

from backend import config
from backend.models.enums import Importance
from backend.models.prediction import Prediction
from backend.models.task import Task

logger = logging.getLogger(__name__)

# Used only when there's no history at all to fall back on (brand-new install).
DEFAULT_HOURS_BY_IMPORTANCE = {
    Importance.LOW: 0.5,
    Importance.MEDIUM: 1.5,
    Importance.HIGH: 3.0,
    Importance.CRITICAL: 4.0,
}

# How many matching historical samples count as "fully confident". Below
# this, confidence scales down linearly rather than jumping straight to 1.0
# off a single data point.
_CONFIDENT_SAMPLE_SIZE = 5


# In-process cache for the trained model, reloaded automatically if the
# file's mtime changes (ml/trainer.py overwrites it weekly while the API
# server keeps running for days/weeks between restarts).
_trained_cache: Optional[dict] = None
_trained_cache_mtime: Optional[float] = None


def _load_trained_model() -> Optional[dict]:
    global _trained_cache, _trained_cache_mtime

    from backend.ml.trainer import ESTIMATOR_MODEL_PATH

    if not ESTIMATOR_MODEL_PATH.exists():
        return None

    mtime = ESTIMATOR_MODEL_PATH.stat().st_mtime
    if _trained_cache is not None and mtime == _trained_cache_mtime:
        return _trained_cache

    try:
        import joblib

        _trained_cache = joblib.load(ESTIMATOR_MODEL_PATH)
        _trained_cache_mtime = mtime
        return _trained_cache
    except Exception as exc:  # noqa: BLE001 - a corrupt/incompatible pickle shouldn't break estimation
        logger.warning(
            "ml.estimator: failed to load trained model at %s (%s); falling back to group-median",
            ESTIMATOR_MODEL_PATH,
            exc,
        )
        return None


def _predict_from_trained_model(task: Task) -> Optional[tuple[float, float]]:
    """Returns (predicted_hours, confidence_score) from the trained model, or None if unavailable."""
    bundle = _load_trained_model()
    if bundle is None:
        return None

    from backend.ml.trainer import build_feature_row

    try:
        predicted = float(bundle["model"].predict([build_feature_row(task)])[0])
    except Exception as exc:  # noqa: BLE001 - feature-shape drift, corrupt bundle, etc.
        logger.warning("ml.estimator: trained model prediction failed (%s); falling back", exc)
        return None

    if predicted <= 0:
        return None

    # Confidence scales with how much data the model was trained on, capped
    # below 1.0 — this tier is a smarter fallback, not the most-specific
    # signal available (project-specific median still wins when it exists).
    sample_count = bundle.get("sample_count", 20)
    confidence = min(0.85, 0.4 + sample_count / 200)
    return round(predicted, 2), round(confidence, 2)


def _completed_hours(db: Session, *, project_id: Optional[int] = None, importance: Optional[Importance] = None) -> List[float]:
    query = db.query(Task.actual_hours).filter(Task.actual_hours.isnot(None))
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if importance is not None:
        query = query.filter(Task.importance == importance)
    return [row[0] for row in query.all() if row[0] is not None and row[0] > 0]


def estimate_hours(db: Session, task: Task) -> tuple[float, float]:
    """
    Return (predicted_hours, confidence_score) for `task`.

    Tries, in order: the user's own completed tasks in the same project,
    then completed tasks of the same importance tier (any project), then
    a flat importance-based default. Confidence reflects how much of that
    ladder had to be climbed and how many samples backed the estimate.
    """
    if task.project_id is not None:
        samples = _completed_hours(db, project_id=task.project_id)
        if samples:
            predicted = statistics.median(samples)
            confidence = min(1.0, 0.5 + 0.1 * len(samples)) if len(samples) < _CONFIDENT_SAMPLE_SIZE else 1.0
            return round(predicted, 2), round(confidence, 2)

    trained = _predict_from_trained_model(task)
    if trained is not None:
        return trained

    samples = _completed_hours(db, importance=task.importance)
    if samples:
        predicted = statistics.median(samples)
        confidence = min(0.7, 0.3 + 0.08 * len(samples))
        return round(predicted, 2), round(confidence, 2)

    predicted = DEFAULT_HOURS_BY_IMPORTANCE.get(task.importance, config.DEFAULT_TASK_HOURS)
    return round(predicted, 2), 0.2


def ensure_estimate(db: Session, task: Task, *, log: bool = True) -> Task:
    """
    Fill in task.estimated_hours / confidence_score if either is missing,
    and log a Prediction row so the estimate can later be scored against
    reality. Does not commit — callers batch-commit after processing a
    set of tasks (see services/scheduler_service.py).
    """
    if task.estimated_hours is None or task.confidence_score is None:
        predicted, confidence = estimate_hours(db, task)
        task.estimated_hours = task.estimated_hours if task.estimated_hours is not None else predicted
        task.confidence_score = confidence

        if log:
            db.add(
                Prediction(
                    task_id=task.id,
                    category=str(task.project_id) if task.project_id else task.importance.value,
                    predicted_hours=task.estimated_hours,
                )
            )
    return task


def resolve_prediction(db: Session, task: Task) -> None:
    """
    Called when a task completes (task.actual_hours is now known):
    backfills the most recent unresolved Prediction for this task with
    actual_hours and error_pct, so ml/trainer.py (Milestone 8) has a
    clean (predicted, actual) pair. No-op if there's nothing to resolve
    or actual_hours was never recorded.
    """
    if task.actual_hours is None:
        return

    prediction = (
        db.query(Prediction)
        .filter(Prediction.task_id == task.id, Prediction.resolved_at.is_(None))
        .order_by(Prediction.created_at.desc())
        .first()
    )
    if prediction is None:
        return

    from datetime import datetime, timezone

    prediction.actual_hours = task.actual_hours
    if prediction.predicted_hours:
        prediction.error_pct = round(
            (task.actual_hours - prediction.predicted_hours) / prediction.predicted_hours * 100, 2
        )
    prediction.resolved_at = datetime.now(timezone.utc)
