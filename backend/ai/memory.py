"""
ai/memory.py — Short-term working memory for the AI pipeline (PRD §63
"Short-Term Memory": today's schedule, current project, current task,
recent conversations, recent changes).

This was a docstring-only stub; the coach re-derived everything from
scratch on every message and had no way to resolve a follow-up like
"can I finish it by Friday?" after already having named a task earlier
in the conversation. This fills that gap in.

Deliberately process-local, in-memory, and NOT persisted to the
database. BrainDUMP is a local-first, single-user app that runs as one
long-lived backend process -- an in-process singleton is the simplest
thing that satisfies what PRD §63 actually asks for ("recent"
conversations/changes within a working session), without building
multi-session or multi-user infrastructure nothing here needs. A
restart clearing it is correct behavior for short-term memory: durable
facts (estimation history, preferred hours, recurring projects) belong
in the database via ml/estimator.py and friends, not here. Long-term /
episodic / semantic memory (PRD §63's other three tiers) are separate,
larger builds -- this module only covers the short-term tier.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, List, Optional


@dataclass
class ConversationTurn:
    role: str  # "user" | "coach"
    message: str
    agent: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkingMemory:
    """Short-term context for a single ongoing session with the coach."""

    _MAX_TURNS = 20

    def __init__(self) -> None:
        self._turns: Deque[ConversationTurn] = deque(maxlen=self._MAX_TURNS)
        self.current_task_id: Optional[int] = None
        self.current_task_title: Optional[str] = None
        self.current_project_id: Optional[int] = None

    # -- conversation history -------------------------------------------------

    def remember_turn(self, role: str, message: str, agent: Optional[str] = None) -> None:
        self._turns.append(ConversationTurn(role=role, message=message, agent=agent))

    def recent_turns(self, limit: int = 6) -> List[ConversationTurn]:
        return list(self._turns)[-limit:]

    def recent_context_text(self, limit: int = 4) -> str:
        """Short plain-text digest of recent turns, for grounding the
        open-ended LLM fallback prompt in what was just discussed."""
        turns = self.recent_turns(limit)
        if not turns:
            return ""
        return "\n".join(f"{t.role}: {t.message}" for t in turns)

    # -- current focus ---------------------------------------------------------

    def set_current_task(
        self,
        task_id: Optional[int],
        title: Optional[str],
        project_id: Optional[int] = None,
    ) -> None:
        """Called whenever an agent resolves a specific task for the
        user (Next Task, Deadline, Replan-at-risk), so a follow-up
        message with a pronoun ("it", "that one") has something to
        resolve against instead of requiring the task to be re-named."""
        self.current_task_id = task_id
        self.current_task_title = title
        self.current_project_id = project_id

    def has_current_task(self) -> bool:
        return self.current_task_id is not None

    def clear(self) -> None:
        self._turns.clear()
        self.current_task_id = None
        self.current_task_title = None
        self.current_project_id = None


# Single shared instance for the process -- see class docstring for why a
# per-process singleton (not a per-request object, not a DB table) is the
# right scope for short-term memory here.
working_memory = WorkingMemory()
