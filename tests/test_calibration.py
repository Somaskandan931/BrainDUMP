"""ml/calibration.py — the personal-bias feedback loop into new estimates."""

from __future__ import annotations

import pytest

from backend.database import owner_id
from backend.ml import calibration, estimator
from backend.ml.calibration import LOOKBACK_DAYS, MAX_ADJUSTMENT_PCT, MIN_SAMPLES, Calibration
from backend.models.enums import Importance
from backend.models.prediction import Prediction
from tests.helpers import make_completed_task, make_project, make_resolved_prediction, make_task


def _history(db, category: str, *, n: int, predicted=2.0, actual=2.6, resolved_days_ago=1.0):
    anchor = make_task(db, f"anchor-{category}")
    for _ in range(n):
        make_resolved_prediction(
            db, anchor, category, predicted=predicted, actual=actual, resolved_days_ago=resolved_days_ago
        )


# --- get_calibration ---------------------------------------------------------


def test_no_calibration_below_min_samples(db):
    _history(db, "high", n=MIN_SAMPLES - 1)
    assert calibration.get_calibration(db, "high") is None


def test_bias_is_signed_mean_of_resolved_errors(db):
    _history(db, "high", n=MIN_SAMPLES, predicted=2.0, actual=2.6)  # +30%
    cal = calibration.get_calibration(db, "high")

    assert cal is not None
    assert cal.bias_pct == pytest.approx(30.0)
    assert cal.sample_count == MIN_SAMPLES
    assert 0 < cal.confidence <= 1


def test_overestimation_gives_negative_bias(db):
    _history(db, "low", n=MIN_SAMPLES, predicted=2.0, actual=1.8)  # -10%
    assert calibration.get_calibration(db, "low").bias_pct == pytest.approx(-10.0)


def test_confidence_grows_with_sample_count_and_caps_at_one(db):
    _history(db, "a", n=3)
    _history(db, "b", n=30)
    assert calibration.get_calibration(db, "a").confidence < calibration.get_calibration(db, "b").confidence
    assert calibration.get_calibration(db, "b").confidence == 1.0


def test_only_the_requested_category_counts(db):
    _history(db, "high", n=MIN_SAMPLES)
    assert calibration.get_calibration(db, "medium") is None


def test_history_outside_lookback_window_is_ignored(db):
    _history(db, "high", n=MIN_SAMPLES, resolved_days_ago=LOOKBACK_DAYS + 5)
    assert calibration.get_calibration(db, "high") is None


def test_unresolved_predictions_do_not_count(db):
    anchor = make_task(db, "anchor")
    for _ in range(MIN_SAMPLES + 2):
        db.add(Prediction(user_id=owner_id(db), task_id=anchor.id, category="high", predicted_hours=2.0))
    db.commit()
    assert calibration.get_calibration(db, "high") is None


# --- apply_calibration -------------------------------------------------------


def test_apply_without_calibration_is_a_no_op():
    assert calibration.apply_calibration(3.0, None) == (3.0, 0.0)


def test_underestimating_user_gets_longer_estimates():
    hours, applied = calibration.apply_calibration(2.0, Calibration("x", 30.0, 5, 0.5))
    assert applied == 30.0
    assert hours == pytest.approx(2.6)


def test_overestimating_user_gets_shorter_estimates():
    hours, applied = calibration.apply_calibration(2.0, Calibration("x", -20.0, 5, 0.5))
    assert applied == -20.0
    assert hours == pytest.approx(1.6)


def test_adjustment_is_clamped_but_true_bias_is_still_reportable():
    cal = Calibration("x", 400.0, 8, 0.8)
    hours, applied = calibration.apply_calibration(2.0, cal)

    assert applied == MAX_ADJUSTMENT_PCT
    assert hours == pytest.approx(2.0 * (1 + MAX_ADJUSTMENT_PCT / 100))
    assert cal.bias_pct == 400.0  # the caller can still show the real number


def test_calibrated_estimate_never_drops_below_the_floor():
    hours, _ = calibration.apply_calibration(0.11, Calibration("x", -60.0, 5, 0.5))
    assert hours >= 0.1


def test_non_positive_base_is_returned_untouched():
    assert calibration.apply_calibration(0.0, Calibration("x", 30.0, 5, 0.5)) == (0.0, 0.0)


# --- category resolution + the loop into the estimator -----------------------


def test_category_is_project_id_when_present_else_importance(db):
    project = make_project(db)
    assert calibration.resolve_category(make_task(db, project=project)) == str(project.id)
    assert calibration.resolve_category(make_task(db, importance=Importance.HIGH)) == "high"


def test_detailed_estimate_applies_the_project_bias(db):
    project = make_project(db, "Research")
    for _ in range(4):
        make_completed_task(db, project=project, estimated_hours=2.0, actual_hours=2.0)
    _history(db, str(project.id), n=MIN_SAMPLES, predicted=2.0, actual=2.6)  # +30%

    task = make_task(db, project=project)
    detail = estimator.estimate_hours_detailed(db, task)

    assert detail["base_tier"] == "project_history"
    assert detail["base_hours"] == pytest.approx(2.0)
    assert detail["calibration_bias_pct"] == pytest.approx(30.0)
    assert detail["calibrated_hours"] == pytest.approx(2.6)


def test_detailed_estimate_without_history_reports_no_calibration(db):
    detail = estimator.estimate_hours_detailed(db, make_task(db, importance=Importance.HIGH))

    assert detail["base_tier"] == "default"
    assert detail["calibration_bias_pct"] is None
    assert detail["calibration_applied_pct"] == 0.0
    assert detail["calibrated_hours"] == detail["base_hours"]


def test_ensure_estimate_stores_the_calibrated_number_and_logs_under_the_same_category(db):
    """The loop only closes if the Prediction is logged under the key
    get_calibration() later looks it up by."""
    project = make_project(db)
    for _ in range(4):
        make_completed_task(db, project=project, estimated_hours=2.0, actual_hours=2.0)
    _history(db, str(project.id), n=MIN_SAMPLES, predicted=2.0, actual=2.6)

    task = make_task(db, project=project)
    estimator.ensure_estimate(db, task)
    db.commit()

    assert task.estimated_hours == pytest.approx(2.6)
    logged = db.query(Prediction).filter(Prediction.task_id == task.id).one()
    assert logged.category == str(project.id)
    assert logged.predicted_hours == pytest.approx(2.6)


def test_user_supplied_estimate_is_never_overwritten(db):
    project = make_project(db)
    _history(db, str(project.id), n=MIN_SAMPLES)
    task = make_task(db, project=project, estimated_hours=5.0, confidence_score=0.9)

    estimator.ensure_estimate(db, task)
    assert task.estimated_hours == 5.0


def test_resolving_a_prediction_backfills_error_pct(db):
    project = make_project(db)
    task = make_task(db, project=project, estimated_hours=2.0, confidence_score=0.5)
    db.add(Prediction(user_id=owner_id(db), task_id=task.id, category=str(project.id), predicted_hours=2.0))
    db.commit()

    task.actual_hours = 3.0
    estimator.resolve_prediction(db, task)
    db.commit()

    resolved = db.query(Prediction).filter(Prediction.task_id == task.id).one()
    assert resolved.actual_hours == 3.0
    assert resolved.error_pct == pytest.approx(50.0)
    assert resolved.resolved_at is not None
