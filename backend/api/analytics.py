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

from backend.database import get_db
from backend.schemas.analytics import (
    EstimationErrorResponse,
    ProductivityHoursResponse,
    StreaksResponse,
    WeeklyReviewResponse,
)
from backend.services import analytics_service

router = APIRouter()


@router.get("/weekly-review", response_model=WeeklyReviewResponse)
def weekly_review(db: Session = Depends(get_db)) -> WeeklyReviewResponse:
    return analytics_service.weekly_review(db)


@router.get("/estimation-error", response_model=EstimationErrorResponse)
def estimation_error(db: Session = Depends(get_db)) -> EstimationErrorResponse:
    return analytics_service.estimation_error(db)


@router.get("/productivity-hours", response_model=ProductivityHoursResponse)
def productivity_hours(db: Session = Depends(get_db)) -> ProductivityHoursResponse:
    return analytics_service.productivity_hours(db)


@router.get("/streaks", response_model=StreaksResponse)
def streaks(db: Session = Depends(get_db)) -> StreaksResponse:
    return analytics_service.streaks(db)
