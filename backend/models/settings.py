"""
models/settings.py — SQLAlchemy model for Setting.

Simple key-value store for user preferences that don't warrant their own
table — e.g. "best_deep_work_hours", "energy_pattern", notification
preferences. Value is stored as a JSON-encoded string and parsed by the
caller; keeping the schema generic here avoids a migration every time a
new preference is added.

user_id + key is the natural key (was just `key`, globally unique,
before multi-user auth) -- each user has their own "best_deep_work_hours"
etc., not one shared row.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.mixins import TimestampMixin


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_settings_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded

    def __repr__(self) -> str:
        return f"<Setting user_id={self.user_id} key={self.key!r}>"
