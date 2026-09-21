"""
api/memory.py — Episodic, Long-Term, and Semantic memory endpoints
(PRD §63).

Short-term memory (ai/memory.py's WorkingMemory) deliberately has no
route here: it's process-local, session-scoped state for the chat
endpoint, not something with its own page. These three routes expose
the *durable* tiers so the frontend can show "what BrainDUMP remembers"
instead of it only ever being consumed internally by the AI coach.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.ai import episodic_memory, long_term_memory, semantic_memory
from backend.api.deps import get_scoped_db
from backend.models.enums import EpisodicEventType, SemanticRelationType
from backend.schemas.memory import EpisodicMemoryResponse, LongTermProfileResponse, SemanticMemoryResponse

router = APIRouter()


@router.get("/episodic", response_model=EpisodicMemoryResponse)
def list_episodic_events(
    event_type: Optional[EpisodicEventType] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_scoped_db),
) -> dict:
    events = episodic_memory.recent_events(db, limit=limit, event_type=event_type)
    return {"events": events}


@router.get("/long-term", response_model=LongTermProfileResponse)
def get_long_term_profile(db: Session = Depends(get_scoped_db)) -> dict:
    profile = long_term_memory.get_profile(db) or long_term_memory.compute_profile(db)
    return profile


@router.get("/semantic", response_model=SemanticMemoryResponse)
def list_semantic_relations(
    relation_type: Optional[SemanticRelationType] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_scoped_db),
) -> dict:
    relations = semantic_memory.recent_relations(db, limit=limit, relation_type=relation_type)
    return {"relations": relations}
