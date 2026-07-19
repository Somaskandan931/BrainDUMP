"""
ml/trainer.py — Retraining pipeline for estimator.py and priority_model.py.

Milestone 8: pulls resolved Prediction rows (predicted_hours AND
actual_hours both set — see ml/estimator.py::resolve_prediction()),
engineers a small numeric feature set from each Prediction's Task, and
fits a RandomForestRegressor to complement ml/estimator.py's group-median
baseline once there's enough logged history for a learned model to
plausibly help. Persisted to MODELS_DIR/estimator.pkl via joblib —
ml/estimator.py loads it lazily and simply doesn't use it (falls back to
the Milestone 5 median approach) whenever the file is missing, fails to
load, or there isn't a model yet. Training never runs inline on a request;
it's triggered weekly (Sundays) from scheduler/nightly.py, since task
history changes slowly enough that daily retraining buys nothing for a
single-user install and just costs a table scan + fit every night.

priority_model.py deliberately stays a hand-tuned weighted sum (see its
own docstring) rather than getting a matching learned version here:
re-weighting its five components would need labeled "what did the user
actually work on next, and why" data broken down per component, and the
schema today only stores the *composite* priority_score on Task /
Prediction.predicted_priority_score — not the five inputs that produced
it. Retrofitting that is a real schema change (and a training-signal
design question: "worked on next" isn't unambiguously logged either), so
it's left as documented future scope rather than smuggled into this
milestone as a half-measure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from backend import config
from backend.models.enums import EnergyLevel, Importance
from backend.models.prediction import Prediction
from backend.models.task import Task

logger = logging.getLogger(__name__)

ESTIMATOR_MODEL_PATH = config.MODELS_DIR / "estimator.pkl"

# Below this many resolved (predicted, actual) pairs, a fitted model has no
# real chance of beating ml/estimator.py's group-median baseline — skip
# training rather than persist something that would just add noise on top
# of a perfectly serviceable fallback.
MIN_TRAINING_SAMPLES = 20

# Below this many samples, skip the held-out train/test split too (there
# isn't enough data left over for a meaningful test set) and just report
# in-sample error — logged/returned as a rough sanity number, not a claim
# of real generalization.
MIN_SAMPLES_FOR_HOLDOUT = 40

_IMPORTANCE_ORDINAL = {
    Importance.LOW: 0.0,
    Importance.MEDIUM: 1.0,
    Importance.HIGH: 2.0,
    Importance.CRITICAL: 3.0,
}
_ENERGY_ORDINAL = {
    EnergyLevel.LOW: 0.0,
    EnergyLevel.MEDIUM: 1.0,
    EnergyLevel.HIGH: 2.0,
}

# Feature order is significant — ml/estimator.py must build vectors the
# same way at inference time. Kept as one flat list (not one-hot per
# project) on purpose: a personal install has too few projects for
# one-hot encoding to generalize, and a brand-new project would otherwise
# break inference the day it's created ("unseen category").
FEATURE_NAMES = ["importance_ordinal", "energy_ordinal", "has_project", "has_deadline"]


def build_feature_row(task: Task) -> list[float]:
    """Turn a Task into the numeric feature vector both trainer and estimator use."""
    return [
        _IMPORTANCE_ORDINAL.get(task.importance, 1.0),
        _ENERGY_ORDINAL.get(task.energy_requirement, 1.0) if task.energy_requirement else 1.0,
        1.0 if task.project_id is not None else 0.0,
        1.0 if task.deadline is not None else 0.0,
    ]


@dataclass
class TrainingResult:
    trained: bool
    sample_count: int
    reason: Optional[str] = None
    mean_absolute_error_hours: Optional[float] = None
    trained_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolved_training_rows(db: Session) -> list[tuple[list[float], float]]:
    rows = (
        db.query(Prediction)
        .options(joinedload(Prediction.task))
        .filter(Prediction.actual_hours.isnot(None), Prediction.resolved_at.isnot(None))
        .all()
    )
    samples: list[tuple[list[float], float]] = []
    for prediction in rows:
        task = prediction.task
        # Guard against orphaned/deleted-task predictions and non-positive
        # actuals (a 0-hour "actual" is a logging artifact, not a real
        # duration a regressor should learn from).
        if task is None or not prediction.actual_hours or prediction.actual_hours <= 0:
            continue
        samples.append((build_feature_row(task), prediction.actual_hours))
    return samples


def train_estimator(db: Session) -> TrainingResult:
    """
    Fit a RandomForestRegressor on resolved Prediction history and persist
    it to ESTIMATOR_MODEL_PATH (joblib). No-op (trained=False, nothing
    written) if there isn't enough history yet — ml/estimator.py keeps
    using the group-median baseline in that case, since that approach
    needs no minimum sample size to be useful.
    """
    samples = _resolved_training_rows(db)
    if len(samples) < MIN_TRAINING_SAMPLES:
        return TrainingResult(
            trained=False,
            sample_count=len(samples),
            reason=f"need {MIN_TRAINING_SAMPLES} resolved predictions to train, have {len(samples)}",
        )

    # Imported lazily so importing backend.ml.trainer (e.g. from
    # ml/estimator.py just to read ESTIMATOR_MODEL_PATH) never pays the
    # sklearn import cost unless a training run actually happens.
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import train_test_split
    import joblib

    X = [row[0] for row in samples]
    y = [row[1] for row in samples]

    if len(samples) >= MIN_SAMPLES_FOR_HOLDOUT:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    else:
        X_train, X_test, y_train, y_test = X, X, y, y

    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=6,
        min_samples_leaf=2,
        random_state=42,
    )
    model.fit(X_train, y_train)
    mae = mean_absolute_error(y_test, model.predict(X_test))

    trained_at = datetime.now(timezone.utc).isoformat()
    config.MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_names": FEATURE_NAMES,
            "trained_at": trained_at,
            "sample_count": len(samples),
            "mean_absolute_error_hours": round(mae, 3),
        },
        ESTIMATOR_MODEL_PATH,
    )

    logger.info(
        "ml.trainer: trained estimator on %d samples (MAE=%.2f hours), saved to %s",
        len(samples),
        mae,
        ESTIMATOR_MODEL_PATH,
    )
    return TrainingResult(
        trained=True,
        sample_count=len(samples),
        mean_absolute_error_hours=round(mae, 3),
        trained_at=trained_at,
    )


if __name__ == "__main__":
    # `python -m backend.ml.trainer` — manual retrain for testing, without
    # waiting for Sunday's nightly job.
    from backend.database import SessionLocal

    session = SessionLocal()
    try:
        print(train_estimator(session).to_dict())
    finally:
        session.close()
