"""
models/prediction.py — SQLAlchemy model for Prediction.

The training table for backend/ml/*. Every time the Estimator Agent
predicts a duration (and, separately, whenever the Priority Engine
scores a task), a row is logged here. Once the task/session completes,
actual_hours and error_pct get backfilled so ml/trainer.py has clean
(predicted, actual) pairs to retrain on — this is the "Learning Model"
described in the product vision (Coding +18%, DSA -15%, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.task import Task


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Grouping key for aggregate error stats, e.g. "DSA", "Assignments",
    # "Coding" — typically the project name or a task category tag.
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    predicted_hours: Mapped[float] = mapped_column(Float, nullable=False)
    actual_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    predicted_priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="predictions")

    def __repr__(self) -> str:
        return f"<Prediction id={self.id} task_id={self.task_id} predicted={self.predicted_hours}>"
