"""
ai/long_term_memory.py — Long-Term Memory tier (PRD §63: "Preferred work
hours, Estimation history, Recurring projects, Frequently used labels,
Average coding speed, Average writing speed, Focus preferences").

This tier was entirely unbuilt -- every fact it describes already exists
*somewhere* in the database (WorkSession, Prediction, Project), but
nothing ever rolled it up into the single profile PRD §63 describes, and
nothing fed it back to the AI coach as "what we know about how this user
works."

Honest scope notes:
- "Frequently used labels" is dropped: models/task.py has no labels
  field anywhere in the schema, so there's nothing real to roll up.
  Adding a fake/empty field for it would be worse than omitting it.
- "Average coding speed" / "average writing speed" -- there's no skill
  taxonomy on Task (no "coding" vs "writing" category), only
  Prediction.category, which is either a project id or an Importance
  value (see analytics_service._category_display_name). The closest
  honest proxy is per-category estimation bias, which is what
  estimation_accuracy below reports; this is *not* a literal typing/
  coding-speed metric, and the field is named accordingly rather than
  pretending to be one.
- "Recurring projects" -- there's no recurrence flag on Project either.
  recent_completed_projects reports real completion history instead of
  guessing at recurrence from name similarity.
- This profile is surfaced to the user (GET /api/memory/long-term),
  folded into the AI coach's context snapshot, AND (see
  derived_energy_pattern() below) wired back into scheduling:
  services/scheduler_service.py uses it in place of
  config.DEFAULT_ENERGY_PATTERN's static curve once there's enough
  logged history to trust it. Below that bar it stays advisory-only and
  the scheduler falls back to the static default, same as before.

Persisted via the existing Setting key-value table (same pattern
scheduler/nightly.py already uses for its run summary) rather than a
dedicated table, since this is a single derived row, recomputed wholesale
each time, with no query pattern that benefits from its own table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.db.database import owner_id
from backend.app.models.enums import ProjectStatus
from backend.app.models.project import Project
from backend.app.models.settings import Setting
from backend.app.services.productivity import analytics_service

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "long_term_memory_profile"
_RECENT_PROJECTS_LIMIT = 5
_PEAK_HOURS_LIMIT = 3


def compute_profile(db: Session) -> dict:
    """Recompute the long-term profile from current data. Read-only —
    does not persist; call persist_profile() (or refresh_profile()) to
    save the result."""
    now = datetime.now(timezone.utc)

    hours = analytics_service.productivity_hours(db)
    active_hours = [b for b in hours.by_hour if b.sessions_count > 0]
    peak_hours = [
        b.hour
        for b in sorted(active_hours, key=lambda b: b.hours_logged, reverse=True)[:_PEAK_HOURS_LIMIT]
    ]
    # How many real logged WorkSessions the peak-hour calculation above is
    # actually backed by -- derived_energy_pattern() uses this to decide
    # whether there's enough history to override the scheduler's static
    # default curve, the same way estimation bias below isn't acted on
    # until it clears analytics_service's own noise threshold.
    peak_hours_sample_size = sum(b.sessions_count for b in active_hours)

    errors = analytics_service.estimation_error(db)
    worst_bias = max(errors.by_category, key=lambda c: abs(c.average_error_pct), default=None)

    completed_projects = (
        db.query(Project)
        .filter(Project.status == ProjectStatus.COMPLETED)
        .order_by(Project.updated_at.desc())
        .limit(_RECENT_PROJECTS_LIMIT)
        .all()
    )

    streaks = analytics_service.streaks(db)

    return {
        "generated_at": now.isoformat(),
        "preferred_work_hours": peak_hours,
        "peak_hours_sample_size": peak_hours_sample_size,
        "estimation_accuracy": {
            "overall_average_error_pct": errors.overall_average_error_pct,
            "sample_count": errors.overall_sample_count,
            "most_biased_category": worst_bias.category if worst_bias else None,
            "most_biased_direction": worst_bias.bias if worst_bias else None,
        },
        "recent_completed_projects": [p.name for p in completed_projects],
        "longest_streak_days": streaks.longest_streak_days,
    }


def persist_profile(db: Session, profile: dict) -> Setting:
    setting = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
    if setting is None:
        setting = Setting(user_id=owner_id(db), key=_SETTINGS_KEY, value=json.dumps(profile))
        db.add(setting)
    else:
        setting.value = json.dumps(profile)
    db.commit()
    return setting


def refresh_profile(db: Session) -> dict:
    """Recompute and persist in one call — what the nightly job and the
    on-demand API endpoint both want."""
    profile = compute_profile(db)
    persist_profile(db, profile)
    return profile


def get_profile(db: Session) -> Optional[dict]:
    """Last-persisted profile, or None if it's never been computed yet
    (e.g. brand new install, nightly job hasn't run)."""
    setting = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
    if setting is None or not setting.value:
        return None
    try:
        return json.loads(setting.value)
    except (TypeError, ValueError) as exc:
        logger.warning("long_term_memory: couldn't parse stored profile (%s)", exc)
        return None


# Below this many logged WorkSessions behind the peak-hour calculation,
# overriding config.DEFAULT_ENERGY_PATTERN's whole-day curve off that
# little data risks acting on noise (e.g. 2 late-night sessions in the
# last 30 days shouldn't relabel 11pm as this user's peak hour). Same
# "don't act on noise" bar analytics_service.py applies to estimation
# bias, chosen for the same reason: a handful of data points is not a
# pattern.
_MIN_SESSIONS_FOR_ENERGY_OVERRIDE = 10


def derived_energy_pattern(profile: dict) -> Optional[dict]:
    """
    Translate `profile["preferred_work_hours"]` into a full 0-23
    hour->EnergyLevel-string pattern, in the same shape as
    config.DEFAULT_ENERGY_PATTERN, for ml/priority_model.py's
    energy_pattern parameter.

    Peak hours (the top real logged-work hours) are marked "high"; the
    hour immediately before/after a peak hour is marked "medium" (energy
    doesn't cliff-edge on either side of a peak); everything else is
    "low". This is coarser than the default's shaped morning/afternoon/
    evening curve, but it's derived from what the user actually did
    rather than assumed.

    Returns None -- caller falls back to config.DEFAULT_ENERGY_PATTERN --
    when there are no peak hours yet, or too few logged sessions behind
    them to trust the result (see _MIN_SESSIONS_FOR_ENERGY_OVERRIDE).
    """
    peak_hours = profile.get("preferred_work_hours") or []
    sample_size = profile.get("peak_hours_sample_size", 0)
    if not peak_hours or sample_size < _MIN_SESSIONS_FOR_ENERGY_OVERRIDE:
        return None

    peak_set = set(peak_hours)
    adjacent = {(h + 1) % 24 for h in peak_hours} | {(h - 1) % 24 for h in peak_hours}
    adjacent -= peak_set  # a peak hour stays "high" even if it's adjacent to another peak

    pattern: dict[int, str] = {}
    for hour in range(24):
        if hour in peak_set:
            pattern[hour] = "high"
        elif hour in adjacent:
            pattern[hour] = "medium"
        else:
            pattern[hour] = "low"
    return pattern


def recall_context_text(db: Session) -> str:
    """Short plain-text digest of the long-term profile, for the AI
    coach's context snapshot -- falls back to a fresh (unpersisted)
    computation if nothing's been saved yet, so a brand-new install
    still gets a real answer instead of nothing."""
    profile = get_profile(db) or compute_profile(db)

    parts = []
    if profile.get("preferred_work_hours"):
        parts.append(f"peak hours: {profile['preferred_work_hours']}")
    bias = profile.get("estimation_accuracy", {})
    if bias.get("most_biased_category"):
        parts.append(f"tends to {bias['most_biased_direction']} {bias['most_biased_category']}")
    if profile.get("recent_completed_projects"):
        parts.append(f"recently finished: {', '.join(profile['recent_completed_projects'][:3])}")
    if not parts:
        return ""
    return "; ".join(parts)
