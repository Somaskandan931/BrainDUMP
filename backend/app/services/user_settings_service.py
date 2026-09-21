"""
services/user_settings_service.py — Settings page backend.

Two logical resources, both stored as JSON blobs on the existing
generic `Setting` key-value table (see models/settings.py and
ai/long_term_memory.py::persist_profile for the same pattern):

- "user_profile_settings": UserSettingsRead fields (profile, appearance,
  working hours).
- "time_blocks": a JSON list of TimeBlockRead dicts.

get_working_hours()/get_blocked_ranges_for_day() are what
services/scheduler_service.py calls instead of the old hardcoded
config.WORK_DAY_START_HOUR/END_HOUR + config.LUNCH_START_HOUR/END_HOUR
— falling back to those same config defaults whenever a setting hasn't
been touched yet, so an unconfigured install schedules exactly like it
did before this feature existed.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import List

from sqlalchemy.orm import Session

from backend.database import owner_id
from backend.models.settings import Setting
from backend.schemas.user_settings import TimeBlockCreate, TimeBlockRead, UserSettingsRead, UserSettingsUpdate

_PROFILE_KEY = "user_profile_settings"
_TIME_BLOCKS_KEY = "time_blocks"


# ---------------------------------------------------------------------------
# Profile / appearance / working hours
# ---------------------------------------------------------------------------

def get_settings(db: Session) -> UserSettingsRead:
    row = db.query(Setting).filter(Setting.key == _PROFILE_KEY).first()
    if row is None or not row.value:
        return UserSettingsRead()
    try:
        return UserSettingsRead(**json.loads(row.value))
    except (TypeError, ValueError):
        return UserSettingsRead()


def update_settings(db: Session, payload: UserSettingsUpdate) -> UserSettingsRead:
    current = get_settings(db)
    merged = current.model_copy(update=payload.model_dump(exclude_unset=True, exclude_none=True))

    row = db.query(Setting).filter(Setting.key == _PROFILE_KEY).first()
    if row is None:
        row = Setting(user_id=owner_id(db), key=_PROFILE_KEY, value=merged.model_dump_json())
        db.add(row)
    else:
        row.value = merged.model_dump_json()
    db.commit()
    return merged


# ---------------------------------------------------------------------------
# Time blocks
# ---------------------------------------------------------------------------

def _load_time_blocks(db: Session) -> List[dict]:
    row = db.query(Setting).filter(Setting.key == _TIME_BLOCKS_KEY).first()
    if row is None or not row.value:
        return []
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return []


def _save_time_blocks(db: Session, blocks: List[dict]) -> None:
    row = db.query(Setting).filter(Setting.key == _TIME_BLOCKS_KEY).first()
    if row is None:
        row = Setting(user_id=owner_id(db), key=_TIME_BLOCKS_KEY, value=json.dumps(blocks))
        db.add(row)
    else:
        row.value = json.dumps(blocks)
    db.commit()


def list_time_blocks(db: Session) -> List[TimeBlockRead]:
    return [TimeBlockRead(**b) for b in _load_time_blocks(db)]


def create_time_block(db: Session, payload: TimeBlockCreate) -> TimeBlockRead:
    block = TimeBlockRead(id=uuid.uuid4().hex[:12], **payload.model_dump())
    blocks = _load_time_blocks(db)
    blocks.append(json.loads(block.model_dump_json()))
    _save_time_blocks(db, blocks)
    return block


def delete_time_block(db: Session, block_id: str) -> bool:
    blocks = _load_time_blocks(db)
    remaining = [b for b in blocks if b.get("id") != block_id]
    if len(remaining) == len(blocks):
        return False
    _save_time_blocks(db, remaining)
    return True


# ---------------------------------------------------------------------------
# Scheduler-facing helpers (services/scheduler_service.py)
# ---------------------------------------------------------------------------

def get_working_hours(db: Session, on: date) -> tuple[int, int]:
    """(start_hour, end_hour) for the given calendar date, weekday vs.
    weekend, from Settings — falling back to config.WORK_DAY_START_HOUR/
    END_HOUR (both are that same default until Settings is saved once)."""
    settings = get_settings(db)
    is_weekend = on.weekday() >= 5
    if is_weekend:
        return settings.weekend_start_hour, settings.weekend_end_hour
    return settings.weekday_start_hour, settings.weekday_end_hour


def get_blocked_ranges_for_day(db: Session, on: date) -> List[tuple]:
    """(start_minute, end_minute) ranges — minutes since midnight — for
    every time block that applies to this weekday. Caller (scheduler)
    converts to actual datetimes; kept as bare minutes here since this
    function has no timezone to attach them to on its own."""
    weekday = on.weekday()
    ranges = []
    for block in _load_time_blocks(db):
        if weekday not in block.get("days_of_week", []):
            continue
        sh, sm = (int(x) for x in block["start_time"].split(":"))
        eh, em = (int(x) for x in block["end_time"].split(":"))
        ranges.append((sh * 60 + sm, eh * 60 + em))
    return ranges
