"""
api/analytics.py — Analytics & weekly review endpoints.

Milestone 8: wired to backend/services/analytics_service.py, which reads
backend/models/metrics.py (ProductivityMetric) plus Task/Prediction/
WorkSession directly. All four routes are parameterless GETs — there's
nothing for the user to configure, only a single-user history to read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_scoped_db
from backend.schemas.analytics import (
    EstimationErrorResponse,
    EstimationErrorTrendResponse,
    ProductivityHoursResponse,
    StreaksResponse,
    WeeklyReviewResponse,
)
from backend.schemas.execution_score import ExecutionScoreResponse, ExecutionScoreTrendResponse
from backend.schemas.workload import WorkloadResponse
from backend.services import analytics_service, execution_score_service, workload_service

router = APIRouter()


@router.get("/weekly-review", response_model=WeeklyReviewResponse)
def weekly_review(db: Session = Depends(get_scoped_db)) -> WeeklyReviewResponse:
    return analytics_service.weekly_review(db)


@router.get("/estimation-error", response_model=EstimationErrorResponse)
def estimation_error(db: Session = Depends(get_scoped_db)) -> EstimationErrorResponse:
    return analytics_service.estimation_error(db)


@router.get("/estimation-error/trend", response_model=EstimationErrorTrendResponse)
def estimation_error_trend(db: Session = Depends(get_scoped_db)) -> dict:
    """
    Historical estimation error, one point per day (nightly-job snapshots
    plus a live-computed point for today) -- the trend view flagged as
    still open after Execution Score got one but estimation error didn't.
    """
    return {"points": analytics_service.get_estimation_error_trend(db)}


@router.get("/calibration")
def personal_calibration(db: Session = Depends(get_scoped_db)) -> dict:
    """
    Personal Calibration (review #17): the signed per-category bias
    ml/calibration.py is actually applying to new estimates right now,
    e.g. "Research: +34% (12 samples)". Distinct from /estimation-error
    above, which reports the full history regardless of whether it clears
    the calibration module's own confidence gate.
    """
    return {"categories": analytics_service.personal_calibration(db)}


@router.get("/productivity-hours", response_model=ProductivityHoursResponse)
def productivity_hours(db: Session = Depends(get_scoped_db)) -> ProductivityHoursResponse:
    return analytics_service.productivity_hours(db)


@router.get("/streaks", response_model=StreaksResponse)
def streaks(db: Session = Depends(get_scoped_db)) -> StreaksResponse:
    return analytics_service.streaks(db)


@router.get("/workload", response_model=WorkloadResponse)
def workload(db: Session = Depends(get_scoped_db)) -> WorkloadResponse:
    """
    The Workload Engine (PRD Milestone 4): daily/weekly/monthly capacity
    vs. allocated hours, for the dashboard heatmap.
    """
    return workload_service.get_workload(db)


@router.get("/execution-score", response_model=ExecutionScoreResponse)
def execution_score(db: Session = Depends(get_scoped_db)) -> dict:
    """
    The Execution Score (PRD §15/§37, Algorithm 8) — the dashboard hero
    metric. See services/execution_score_service.py for how the 0-100
    number is actually composed from real scheduling/deadline/analytics
    data (the PRD names the ingredients but gives no formula to follow).
    """
    return execution_score_service.compute_execution_score(db).to_dict()


@router.get("/execution-score/trend", response_model=ExecutionScoreTrendResponse)
def execution_score_trend(db: Session = Depends(get_scoped_db)) -> dict:
    """
    Historical Execution Score, one point per day (nightly-job snapshots
    plus a live-computed point for today) -- the trend view flagged as
    the natural follow-up once the score itself existed.
    """
    points = execution_score_service.get_execution_score_trend(db)
    return {"points": [p.to_dict() for p in points]}