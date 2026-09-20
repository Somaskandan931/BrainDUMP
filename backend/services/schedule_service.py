"""
services/schedule_service.py — the "Start your day" lock behind the
Today dashboard's Deadlines panel.

Two operations, both idempotent for a given calendar date:
  - get_today_plan(): read-only, never creates a row. A day nobody has
    started yet just reports buffer_multiplier=1.0 (Default), locked=False.
  - start_day(): the only writer. First call for a date creates the
    DailyPlan row and stamps started_at; every later call the same day
    is a no-op that returns the existing (already-locked) row — once
    locked, the buffer setting and anchor time don't move, even if the
    frontend resends a different multiplier.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.daily_plan import DailyPlan
from backend.schemas.schedule import BUFFER_MULTIPLIERS


def _today() -> date:
    # Local time, not UTC: "today" on a personal daily-planning app
    # means the user's calendar day, and this is a local-first,
    # single-user app (see app.py CORS comment) with no timezone
    # field anywhere else in the schema either.
    return datetime.now().date()


def get_today_plan(db: Session) -> DailyPlan:
    """Read-only lookup; returns an unsaved default DailyPlan (not yet
    persisted) if today hasn't been started, so callers always get a
    plan_date/buffer_multiplier/started_at shape without a null-check."""
    plan = db.query(DailyPlan).filter(DailyPlan.plan_date == _today()).first()
    if plan is not None:
        return plan
    return DailyPlan(plan_date=_today(), buffer_multiplier=1.0, started_at=None)


def start_day(db: Session, buffer_multiplier: float) -> DailyPlan:
    if round(buffer_multiplier, 2) not in [round(m, 2) for m in BUFFER_MULTIPLIERS]:
        raise HTTPException(
            status_code=400,
            detail=f"buffer_multiplier must be one of {BUFFER_MULTIPLIERS}",
        )

    today = _today()
    plan = db.query(DailyPlan).filter(DailyPlan.plan_date == today).first()
    if plan is not None and plan.started_at is not None:
        # Already locked for today — the slider is disabled client-side
        # once this happens, but don't trust that; just hand back what
        # was already locked in instead of silently changing it.
        return plan

    if plan is None:
        plan = DailyPlan(plan_date=today, buffer_multiplier=buffer_multiplier)
        db.add(plan)
    else:
        plan.buffer_multiplier = buffer_multiplier

    plan.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan
