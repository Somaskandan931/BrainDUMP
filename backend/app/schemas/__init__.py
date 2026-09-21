"""
schemas/ — Pydantic request/response models for the API layer.

Kept separate from backend/models/ (the SQLAlchemy ORM layer) on
purpose: ORM models describe what's stored, schemas describe what's
exposed over HTTP. They usually overlap but shouldn't be the same
class — e.g. a TaskCreate schema doesn't accept priority_score (the
system computes that), while TaskRead returns it.
"""

from backend.app.schemas.project import ProjectCreate, ProjectUpdate, ProjectRead
from backend.app.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskRead,
    TaskReorderRequest,
    SubtaskCreate,
    SubtaskUpdate,
    SubtaskRead,
)
from backend.app.schemas.calendar import (
    CalendarEventRead,
    CalendarSyncResponse,
    CreateSessionEventRequest,
)
from backend.app.schemas.analytics import (
    ProjectProgress,
    WeeklyReviewResponse,
    CategoryEstimationError,
    EstimationErrorResponse,
    EstimationErrorTrendPoint,
    EstimationErrorTrendResponse,
    StreaksResponse,
    HourBucket,
    ProductivityHoursResponse,
)
from backend.app.schemas.memory import (
    EpisodicEventRead,
    EpisodicMemoryResponse,
    EstimationAccuracySummary,
    LongTermProfileResponse,
    SemanticRelationRead,
    SemanticMemoryResponse,
)
from backend.app.schemas.schedule import DailyPlanRead, StartDayRequest, BUFFER_MULTIPLIERS

__all__ = [
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectRead",
    "TaskCreate",
    "TaskUpdate",
    "TaskRead",
    "TaskReorderRequest",
    "SubtaskCreate",
    "SubtaskUpdate",
    "SubtaskRead",
    "CalendarEventRead",
    "CalendarSyncResponse",
    "CreateSessionEventRequest",
    "ProjectProgress",
    "WeeklyReviewResponse",
    "CategoryEstimationError",
    "EstimationErrorResponse",
    "EstimationErrorTrendPoint",
    "EstimationErrorTrendResponse",
    "StreaksResponse",
    "HourBucket",
    "ProductivityHoursResponse",
    "EpisodicEventRead",
    "EpisodicMemoryResponse",
    "EstimationAccuracySummary",
    "LongTermProfileResponse",
    "SemanticRelationRead",
    "SemanticMemoryResponse",
    "DailyPlanRead",
    "StartDayRequest",
    "BUFFER_MULTIPLIERS",
]
