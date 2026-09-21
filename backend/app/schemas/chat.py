"""
schemas/chat.py — Pydantic schemas for POST /api/chat (AI Execution Coach, PRD §24).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    agent: str
    message: str
    data: Optional[dict] = None
