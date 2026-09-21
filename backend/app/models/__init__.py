"""
models/__init__.py — Imports every model so Base.metadata is fully
populated wherever this package is imported (database.init_db() relies
on this).
"""

from backend.app.models.user import User
from backend.app.models.project import Project
from backend.app.models.task import Task, Subtask
from backend.app.models.dependency import Dependency
from backend.app.models.session import WorkSession
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.prediction import Prediction
from backend.app.models.metrics import ProductivityMetric
from backend.app.models.settings import Setting
from backend.app.models.memory import EpisodicMemory, SemanticMemory
from backend.app.models.daily_plan import DailyPlan
from backend.app.models.usage import UsageRecord
from backend.app.models.activity import ActivityLog

__all__ = [
    "User",
    "Project",
    "Task",
    "Subtask",
    "Dependency",
    "WorkSession",
    "CalendarEvent",
    "Prediction",
    "ProductivityMetric",
    "Setting",
    "EpisodicMemory",
    "SemanticMemory",
    "DailyPlan",
    "UsageRecord",
    "ActivityLog",
]