"""
api/schedule.py — the Today dashboard's "Start your day" lock.

Two routes, both operating on *today's* DailyPlan (backend/models/
daily_plan.py) — there's no {date} path param because the Today
dashboard only ever cares about the current day; historical plans
aren't exposed anywhere yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.v1.deps import get_scoped_db
from backend.app.models.daily_plan import DailyPlan
from backend.app.schemas.schedule import DailyPlanRead, StartDayRequest
from backend.app.services.planning import schedule_service

router = APIRouter()


@router.get("/today", response_model=DailyPlanRead)
def get_today_plan(db: Session = Depends(get_scoped_db)) -> DailyPlan:
    return schedule_service.get_today_plan(db)


@router.post("/start-day", response_model=DailyPlanRead)
def start_day(payload: StartDayRequest, db: Session = Depends(get_scoped_db)) -> DailyPlan:
    return schedule_service.start_day(db, payload.buffer_multiplier)
