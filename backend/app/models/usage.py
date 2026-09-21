"""
models/usage.py — SQLAlchemy model for UsageRecord.

One row per user per UTC calendar day, incremented every time
ai/ollama_client.call_model() completes a real provider call on behalf
of that user (see services/usage_service.py). Backs the daily AI-call
cap (config.AI_DAILY_CALL_LIMIT) and, longer-term, whatever usage
display Settings ends up showing -- deliberately a coarse daily rollup,
not a row per call, since nothing today needs per-call granularity and
a row-per-call table would grow unbounded for an active user.

token counts are best-effort: OpenRouter's response includes a `usage`
block on success, but not on every code path (e.g. a request that fails
before a response body exists), so both columns default to 0 and are
only ever incremented, never relied on as an exact ledger.
"""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base
from backend.app.models.mixins import TimestampMixin


class UsageRecord(Base, TimestampMixin):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_usage_records_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    ai_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<UsageRecord user_id={self.user_id} date={self.date} ai_calls={self.ai_calls}>"
