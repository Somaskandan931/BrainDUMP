"""
models/settings.py — SQLAlchemy model for Setting.

Simple key-value store for user preferences that don't warrant their own
table — e.g. "best_deep_work_hours", "energy_pattern", notification
preferences. Value is stored as a JSON-encoded string and parsed by the
caller; keeping the schema generic here avoids a migration every time a
new preference is added.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.mixins import TimestampMixin


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r}>"
