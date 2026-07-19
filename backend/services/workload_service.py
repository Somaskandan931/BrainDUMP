"""
services/workload_service.py — The Workload Engine (PRD Milestone 4).

Answers "how full are my next few days/weeks/month" by comparing each
day's scheduling capacity (config.WORK_DAY_START_HOUR..WORK_DAY_END_HOUR,
same working-hours window scheduler_service packs into) against the
hours actually allocated to it — real CalendarEvents of any source
(BRAIN_DUMP blocks the scheduler created, plus any synced GOOGLE events),
not just estimated task load. That's the honest "how full is my day"
question: a Google Calendar meeting eats capacity exactly like a
scheduled work block does.

Deliberately reuses scheduler_service's own free-slot math for the
"capacity minus busy = free" arithmetic so this never silently drifts
from what the scheduler/deadline engine consider available.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend import config
from backend.schemas.workload import WorkloadDay, WorkloadPeriod, WorkloadResponse
from backend.services import scheduler_service

DAILY_CAPACITY_HOURS = (config.WORK_DAY_END_HOUR - config.WORK_DAY_START_HOUR)

# Utilization thresholds -> qualitative level, matching the deadline
# engine's own "don't overstate precision, just say the useful thing"
# style (safe/tight/impossible there; light/moderate/full/overloaded here).
_LEVEL_THRESHOLDS = (
    (50.0, "light"),
    (80.0, "moderate"),
    (100.0, "full"),
)


def _level_for(utilization_pct: float) -> str:
    for ceiling, level in _LEVEL_THRESHOLDS:
        if utilization_pct <= ceiling:
            return level
    return "overloaded"


def _allocated_hours_by_day(db: Session, start: datetime, days: int) -> dict:
    """
    Sum busy minutes (any CalendarEvent source) per calendar day over
    [start, start + days), clipped to each day's working-hour window so
    a meeting that runs past WORK_DAY_END_HOUR doesn't inflate the
    percentage past what the day could ever hold.
    """
    end = start + timedelta(days=days)
    busy = scheduler_service.get_busy_intervals(db, start, end)

    totals: dict = {}
    current_day = start.date()
    last_day = end.date()

    while current_day <= last_day:
        day_window_start = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=config.WORK_DAY_START_HOUR
        )
        day_window_end = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=config.WORK_DAY_END_HOUR
        )
        window_start = max(day_window_start, start)
        window_end = min(day_window_end, end)

        if window_start < window_end:
            day_minutes = 0.0
            for b_start, b_end in busy:
                overlap_start = max(b_start, window_start)
                overlap_end = min(b_end, window_end)
                if overlap_end > overlap_start:
                    day_minutes += (overlap_end - overlap_start).total_seconds() / 60.0
            if day_minutes > 0:
                totals[current_day] = day_minutes

        current_day += timedelta(days=1)

    return totals


def get_workload(db: Session, now: Optional[datetime] = None, days: int = 7) -> WorkloadResponse:
    now = now or datetime.now(timezone.utc)
    start_day = now.date()

    monthly_days = max(days, 30)
    allocated_by_day = _allocated_hours_by_day(db, now, monthly_days)

    daily_entries: List[WorkloadDay] = []
    for offset in range(days):
        d = start_day + timedelta(days=offset)
        allocated_minutes = allocated_by_day.get(d, 0.0)
        allocated_hours = round(allocated_minutes / 60.0, 2)
        utilization = round(
            (allocated_hours / DAILY_CAPACITY_HOURS) * 100 if DAILY_CAPACITY_HOURS else 0.0, 1
        )
        daily_entries.append(
            WorkloadDay(
                date=d,
                weekday=d.strftime("%a"),
                capacity_hours=float(DAILY_CAPACITY_HOURS),
                allocated_hours=allocated_hours,
                utilization_pct=utilization,
                level=_level_for(utilization),
            )
        )

    week = _period_summary("This week", daily_entries)

    month_allocated = round(sum(allocated_by_day.values()) / 60.0, 2)
    month_capacity = float(DAILY_CAPACITY_HOURS * monthly_days)
    month_utilization = round((month_allocated / month_capacity) * 100 if month_capacity else 0.0, 1)
    month = WorkloadPeriod(
        label="This month",
        capacity_hours=month_capacity,
        allocated_hours=month_allocated,
        utilization_pct=month_utilization,
        overload_pct=round(month_utilization - 100, 1) if month_utilization > 100 else None,
    )

    peak_day = None
    if daily_entries:
        busiest = max(daily_entries, key=lambda entry: entry.utilization_pct)
        if busiest.utilization_pct > 0:
            peak_day = busiest.weekday

    return WorkloadResponse(days=daily_entries, week=week, month=month, peak_day=peak_day)


def _period_summary(label: str, entries: List[WorkloadDay]) -> WorkloadPeriod:
    capacity = sum(e.capacity_hours for e in entries)
    allocated = sum(e.allocated_hours for e in entries)
    utilization = round((allocated / capacity) * 100 if capacity else 0.0, 1)
    return WorkloadPeriod(
        label=label,
        capacity_hours=round(capacity, 2),
        allocated_hours=round(allocated, 2),
        utilization_pct=utilization,
        overload_pct=round(utilization - 100, 1) if utilization > 100 else None,
    )
