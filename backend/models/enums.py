"""
models/enums.py — Shared enums used across ORM models.

Kept separate from individual model files since several models reference
the same enum (e.g. both Task and Prediction care about task category).
"""

import enum

from sqlalchemy import Enum as SAEnum


def sa_enum(enum_cls):
    """
    SQLAlchemy Enum column type that stores each member's .value (e.g.
    "active") instead of its .name (e.g. "ACTIVE"), which is
    SQLAlchemy's default. Necessary so the stored string matches what
    the Pydantic schemas (backend/schemas/*) validate against, since
    they're built directly on these same str-Enum values.
    """
    return SAEnum(enum_cls, values_callable=lambda e: [member.value for member in e])


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Importance(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EnergyLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventSource(str, enum.Enum):
    """Where a CalendarEvent originated."""
    BRAIN_DUMP = "brain_dump"   # created by the planner/scheduler
    GOOGLE = "google"           # pulled in from Google Calendar
    MANUAL = "manual"           # user-created directly


class SyncStatus(str, enum.Enum):
    NOT_SYNCED = "not_synced"
    SYNCED = "synced"
    ERROR = "error"
