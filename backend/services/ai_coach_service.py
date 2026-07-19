"""
services/ai_coach_service.py — The AI Execution Coach (PRD §24, ⭐⭐⭐).

PRD §24 is explicit that this is NOT a general chatbot: it's a router
in front of specialized agents (Brain Dump, Goal Planner, Deadline,
Scheduler/Replan, Next Task, Analytics), each grounded in the user's
real data, with a constrained LLM fallback for open-ended "answer a
productivity question" cases. This module (and api/chat.py) previously
did not exist at all -- there was no /api/chat route in the codebase,
despite AI Execution Coach being the highest-starred core feature in
the PRD. The frontend's chat page shipped an honest workaround instead
(calling brain-dump/scheduler endpoints directly) -- this fills in the
missing route those quick actions could eventually call through, and
gives the free-text box something real to talk to.

Intent routing here is deliberately simple keyword matching, not an
LLM-based tool-router -- for a single-user local app, a small
regex/keyword dispatch in front of already-correct, already-tested
services (deadline_service, scheduler_service, analytics_service) is
more reliable than asking a small local model to pick the right
function call, and it means the deterministic agents (Next Task,
Replan, Deadline) never hallucinate a wrong number. The open-ended
fallback is the only path that touches the LLM for its response text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.ai.ollama_client import OllamaError, call_model
from backend.ai.prompts import EXECUTION_COACH_SYSTEM, build_execution_coach_prompt
from backend.models.enums import TaskStatus
from backend.models.task import Task
from backend.services import deadline_service, scheduler_service, task_parser

logger = logging.getLogger(__name__)


@dataclass
class CoachResponse:
    agent: str          # which agent handled this: "next_task" | "replan" | "deadline" |
                         # "brain_dump" | "analytics_fallback" | "declined"
    message: str
    data: Optional[dict] = None

    def to_dict(self) -> dict:
        return {"agent": self.agent, "message": self.message, "data": self.data}


_NEXT_TASK_PATTERNS = re.compile(
    r"\b(what('?s| is) next|what should i (work on|do)|next task|do next)\b", re.IGNORECASE
)
_REPLAN_PATTERNS = re.compile(
    r"\b(replan|rebuild (my )?schedule|move everything|re-?plan|i'?m sick|reschedule)\b",
    re.IGNORECASE,
)
_DEADLINE_QUESTION_PATTERNS = re.compile(
    r"\b(can i finish|will i finish|is .* (realistic|feasible|possible)|finish .* before|"
    r"finish .* by)\b",
    re.IGNORECASE,
)


def _handle_next_task(db: Session) -> CoachResponse:
    task = scheduler_service.get_next_task(db)
    if task is None:
        return CoachResponse("next_task", "Nothing active on your list right now — you're clear.")
    return CoachResponse(
        "next_task",
        f'Do this next: "{task.title}"' + (f" (due {task.deadline:%b %d})" if task.deadline else ""),
        data={"task_id": task.id, "title": task.title},
    )


def _handle_replan(db: Session) -> CoachResponse:
    result = deadline_service.replan(db)
    at_risk = result["at_risk_tasks"]
    demoted = result["demoted_tasks"]
    parts = [f"Replanned — {result['rescheduled_count']} task(s) repacked."]
    if demoted:
        parts.append(f"Pushed out {len(demoted)} lower-priority task(s) to make room.")
    if at_risk:
        titles = ", ".join(t.title for t in at_risk[:3])
        parts.append(f"Still at risk: {titles}.")
    else:
        parts.append("Nothing left at risk.")
    return CoachResponse(
        "replan",
        " ".join(parts),
        data={
            "rescheduled_count": result["rescheduled_count"],
            "at_risk_task_ids": [t.id for t in at_risk],
        },
    )


def _find_referenced_task(db: Session, message: str) -> Optional[Task]:
    """
    Best-effort match: find an active task with a deadline whose title
    shares a significant word with the user's message (e.g. "internship
    report" matching a message about "my internship report"). Not fuzzy
    matching/embeddings -- a real semantic match is AI Memory territory
    (ai/embeddings.py, not yet built) -- but good enough to ground a
    deadline answer in a real task instead of guessing.
    """
    candidates = (
        db.query(Task)
        .filter(Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)), Task.deadline.isnot(None))
        .all()
    )
    if not candidates:
        return None

    message_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", message)}
    best, best_overlap = None, 0
    for task in candidates:
        title_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", task.title)}
        overlap = len(message_words & title_words)
        if overlap > best_overlap:
            best, best_overlap = task, overlap
    return best if best_overlap > 0 else None


def _handle_deadline_question(db: Session, message: str) -> Optional[CoachResponse]:
    task = _find_referenced_task(db, message)
    if task is None:
        return None

    plan = deadline_service.compute_deadline_plan(db, task)
    deadline_service.persist_deadline_plan(db, task, plan)
    db.commit()

    default_buffer = next((b for b in plan["buffers"] if b["level"] == "default"), plan["buffers"][0])
    probability_pct = round((task.completion_probability or 0.0) * 100)
    verdict = "Yes." if default_buffer["status"] == "safe" else (
        "It's tight." if default_buffer["status"] == "tight" else "Not as it stands."
    )
    daily = default_buffer.get("suggested_daily_hours")
    daily_clause = f" You need about {daily:.1f}h/day to stay on track." if daily else ""

    return CoachResponse(
        "deadline",
        f'{verdict} Probability {probability_pct}% for "{task.title}".{daily_clause} {default_buffer["message"]}',
        data={"task_id": task.id, "plan": {k: v for k, v in plan.items() if k != "buffers"}},
    )


def _build_context_snapshot(db: Session) -> dict:
    """Compact grounding context for the open-ended LLM fallback — active
    tasks, what's next, what's at risk. Deliberately small: this goes
    into every fallback prompt, so it stays a summary, not a data dump."""
    now = datetime.now(timezone.utc)
    active = (
        db.query(Task).filter(Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS))).all()
    )
    at_risk = deadline_service.detect_at_risk_tasks(db, now)
    next_task = scheduler_service.get_next_task(db)

    return {
        "active_task_count": len(active),
        "at_risk_tasks": [{"title": t.title, "deadline": t.deadline.isoformat() if t.deadline else None} for t in at_risk[:5]],
        "next_task": next_task.title if next_task else None,
    }


def _handle_fallback(db: Session, message: str) -> CoachResponse:
    """
    Open-ended "answer a productivity question" / brain-dump path. If the
    message reads like a brain dump (multiple lines / task-like phrasing),
    route to the Brain Dump agent, same as the frontend's existing
    workaround. Otherwise, ask the constrained Execution Coach LLM,
    grounded in a real snapshot of the user's state.
    """
    looks_like_brain_dump = "\n" in message.strip() or len(message.split()) > 25
    if looks_like_brain_dump:
        try:
            projects, tasks = task_parser.parse_brain_dump(db, message)
            if tasks:
                names = ", ".join(t.title for t in tasks[:5])
                return CoachResponse(
                    "brain_dump",
                    f"Turned that into {len(tasks)} task(s): {names}.",
                    data={"project_count": len(projects), "task_count": len(tasks)},
                )
        except Exception as exc:  # noqa: BLE001 - fall through to coach reply below
            logger.info("Coach: brain-dump routing failed, falling back to coach reply (%s)", exc)

    context = _build_context_snapshot(db)
    try:
        reply = call_model(
            build_execution_coach_prompt(message, json.dumps(context)),
            system=EXECUTION_COACH_SYSTEM,
            json_mode=False,
        )
        return CoachResponse("analytics_fallback", reply.strip(), data=context)
    except OllamaError as exc:
        logger.info("Coach: Ollama unavailable for fallback reply (%s)", exc)
        return CoachResponse(
            "analytics_fallback",
            "The local AI model isn't reachable right now, so I can't answer that one — "
            "but you can still ask 'what's next' or 'replan my week' for the built-in agents.",
            data=context,
        )


def handle_message(db: Session, message: str) -> CoachResponse:
    """
    Single entry point for POST /api/chat. Routes to the matching
    specialized agent (§24's "Supported Agents") in priority order,
    falling back to the constrained LLM coach for anything else.
    """
    message = (message or "").strip()
    if not message:
        return CoachResponse("declined", "Tell me what's on your mind, or ask what to work on next.")

    if _NEXT_TASK_PATTERNS.search(message):
        return _handle_next_task(db)

    if _REPLAN_PATTERNS.search(message):
        return _handle_replan(db)

    if _DEADLINE_QUESTION_PATTERNS.search(message):
        result = _handle_deadline_question(db, message)
        if result is not None:
            return result
        # No matching task found — fall through to the general coach reply
        # rather than a dead end, since the question was still legitimate.

    return _handle_fallback(db, message)
