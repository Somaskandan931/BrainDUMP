"""
schemas/user_settings.py — Settings page: profile, appearance, working
hours, and recurring time blocks.

Backed by the existing generic `Setting` key-value table (see
models/settings.py::Setting and ai/long_term_memory.py for the same
get-or-create-by-key pattern) rather than new dedicated tables — this
is local-first, single-user config, not relational data that needs its
own schema/migration.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

from backend import config

TimeBlockCategory = Literal["meal", "class", "gym", "other"]

# Python's date.weekday() convention: 0=Monday .. 6=Sunday.
Weekday = Literal[0, 1, 2, 3, 4, 5, 6]


class UserSettingsRead(BaseModel):
    display_name: str = ""
    email: str = ""
    dark_mode: bool = True
    # Defaults mirror config.WORK_DAY_START_HOUR/END_HOUR so an
    # unconfigured install schedules exactly like it did before this
    # page existed. Weekend hours have no config precedent — a shorter
    # default day is just a reasonable starting point, editable here.
    weekday_start_hour: int = Field(default=config.WORK_DAY_START_HOUR, ge=0, le=23)
    weekday_end_hour: int = Field(default=config.WORK_DAY_END_HOUR, ge=0, le=23)
    weekend_start_hour: int = Field(default=10, ge=0, le=23)
    weekend_end_hour: int = Field(default=18, ge=0, le=23)


class UserSettingsUpdate(BaseModel):
    """All fields optional — PATCH-style partial update."""

    display_name: str | None = None
    email: str | None = None
    dark_mode: bool | None = None
    weekday_start_hour: int | None = Field(default=None, ge=0, le=23)
    weekday_end_hour: int | None = Field(default=None, ge=0, le=23)
    weekend_start_hour: int | None = Field(default=None, ge=0, le=23)
    weekend_end_hour: int | None = Field(default=None, ge=0, le=23)


class TimeBlockCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    category: TimeBlockCategory = "other"
    # "HH:MM", 24-hour — kept as wall-clock strings at the API boundary
    # since time blocks are local-time-of-day, not UTC instants (unlike
    # CalendarEvent.start_time/end_time).
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: List[Weekday] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])

    @field_validator("days_of_week")
    @classmethod
    def _dedupe_sort(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("days_of_week can't be empty")
        return sorted(set(v))


class TimeBlockRead(TimeBlockCreate):
    id: str
