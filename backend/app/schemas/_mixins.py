"""
schemas/_mixins.py — shared Pydantic serialization helpers.

utc_iso() backs the `@field_serializer` on every *Read schema with
datetime fields, so timestamps read back from SQLite (naive, but UTC in
practice — see backend/utils/timeutil.py) always leave the API with an
explicit UTC offset instead of silently being misread as local time by
the frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.utils.timeutil import ensure_utc


def utc_iso(dt: Optional[datetime]) -> Optional[str]:
    fixed = ensure_utc(dt)
    return fixed.isoformat() if fixed is not None else None
