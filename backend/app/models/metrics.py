"""
models/metrics.py — SQLAlchemy model for ProductivityMetric.

Daily rollup snapshot, written by the nightly job (backend/scheduler/nightly.py)
so Weekly Review / Analytics (Milestone 8) can read pre-aggregated rows
instead of recomputing from raw sessions every time.

One row per user per date now (was per date only, single-user) -- see
uq_productivity_metrics_date's replacement below.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.mixins import TimestampMixin


class ProductivityMetric(Base, TimestampMixin):
    __tablename__ = "productivity_metrics"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_productivity_metrics_user_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    hours_worked: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_planned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0-1.0

    most_productive_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-23
    estimation_error_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Execution Score (PRD §15/§37, Algorithm 8) snapshotted once per day by
    # the nightly job -- see execution_score_service.compute_execution_score().
    execution_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<ProductivityMetric user_id={self.user_id} date={self.date} completion_rate={self.completion_rate}>"
