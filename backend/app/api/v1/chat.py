"""
api/chat.py — AI Execution Coach endpoint (PRD §24, §33/§63: POST /api/chat).

This route did not exist anywhere in the codebase before — the
frontend's chat page (frontend/app/chat/page.tsx) shipped an honest
comment explaining there was "no /api/chat route" and called the
brain-dump/scheduler endpoints directly instead. This fills that gap in
so the coach is a real, grounded endpoint (see services/ai_coach_service.py
for the routing logic) rather than leaving the triple-starred core
feature unimplemented.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.v1.deps import get_scoped_db
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.ai import ai_coach_service

router = APIRouter()


@router.post("/", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_scoped_db)) -> dict:
    result = ai_coach_service.handle_message(db, payload.message)
    return result.to_dict()
