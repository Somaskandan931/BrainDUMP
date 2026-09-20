"""
models/__init__.py — Imports every model so Base.metadata is fully
populated wherever this package is imported (database.init_db() relies
on this).
"""

from backend.models.user import User
from backend.models.project import Project
from backend.models.task import Task, Subtask
from backend.models.dependency import Dependency
from backend.models.session import WorkSession
from backend.models.calendar_event import CalendarEvent
from backend.models.prediction import Prediction
from backend.models.metrics import ProductivityMetric
from backend.models.settings import Setting
from backend.models.memory import EpisodicMemory, SemanticMemory
from backend.models.daily_plan import DailyPlan

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
]