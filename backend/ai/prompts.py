"""
ai/prompts.py — Prompt templates for each specialized agent.

Milestone 4 implements two agents end-to-end:
- Task Parser      (brain dump -> structured tasks, with deadline
                     resolution folded in rather than a separate
                     "Deadline Generator" pass -- one local inference
                     call per brain dump instead of chaining two)
- Goal Breakdown    (single high-level goal -> Project + ordered Task
                     roadmap; this is what ARCHITECTURE.md calls the
                     "Goal Engine")

Milestone 8 adds a third:
- Weekly Review (Reflection Agent) -- turns the week's already-computed
  stats (backend/services/analytics_service.py) into a short natural-
  language recommendation, e.g. "You underestimated Assignments by 28%.
  Start assignments two days earlier." The stats themselves are computed
  in plain Python/SQL, not by the model -- this agent only explains them
  in one sentence. Called through call_model() (not call_model_json():
  the output is prose, not structured data) and wrapped in a
  try/except OllamaError by the caller, which falls back to a
  rule-based sentence if Ollama isn't running -- the analytics page
  should never break just because the local model is offline.

Deferred to later milestones (documented here so the eventual prompt
lives in an obvious place, not built yet):
- Scheduler / Priority Engine agents -- Milestone 5 (scheduler and
  planning engine); these will likely be classical ml/* models rather
  than LLM calls, per ARCHITECTURE.md's ai/ vs ml/ split.
- Daily Planner narration -- the morning job already computes the plan;
  narrating "why" in prose is future scope, not part of Milestone 8.

Every agent here is instructed to return structured JSON only, and
called through backend/ai/ollama_client.call_model_json() with
json_mode=True (Ollama's format="json" constrained decoding), not
relied on as a prompt-only convention.
"""

from __future__ import annotations


# --- Task Parser ---------------------------------------------------------

TASK_PARSER_SYSTEM = """You are the Task Parser agent inside a personal AI operating system.

The user will paste a raw, unstructured "brain dump" -- a stream-of-\
consciousness list of things on their mind. Your job is to extract every \
distinct actionable task from it.

Return ONLY a JSON object with this exact shape, nothing else:
{
  "tasks": [
    {
      "title": string (short, action-oriented, max ~15 words),
      "project_name": string or null (a short project/category name if the \
task clearly belongs to a larger effort, e.g. "SourceUp", "Interview Prep"; \
null for one-off items like "buy groceries"),
      "description": string or null (only if the brain dump gives detail \
beyond the title),
      "importance": one of "low", "medium", "high", "critical" \
(default "medium" unless urgency/stakes are clearly signaled),
      "energy_requirement": one of "low", "medium", "high", or null,
      "deadline": an ISO 8601 datetime string (e.g. "2026-07-25T00:00:00") \
or null. Resolve relative dates ("tomorrow", "next Friday", "in two weeks") \
against the current date/time given below. Only set a deadline if the text \
actually implies one -- do not invent one.,
      "estimated_hours": a number or null (only if the text gives enough \
signal to guess; otherwise null -- do not fabricate a precise number)
    }
  ]
}

Rules:
- One JSON object per distinct task the user mentioned, even if several \
belong to the same project.
- Group tasks under the same project_name (exact same string) when they \
clearly belong to the same effort, so they get linked together.
- Do not merge unrelated tasks into one entry.
- Do not add commentary, markdown, or any text outside the JSON object.
- If nothing actionable is present, return {"tasks": []}.
"""


def build_task_parser_prompt(text: str, current_datetime_iso: str) -> str:
    """User-turn prompt for the Task Parser agent."""
    return (
        f"Current date/time (for resolving relative deadlines): {current_datetime_iso}\n\n"
        f'Brain dump:\n"""\n{text.strip()}\n"""'
    )


# --- Goal Breakdown (Goal Engine) -----------------------------------------

TASK_BREAKDOWN_SYSTEM = """You are the Goal Breakdown agent inside a personal AI operating system.

The user will give you a single high-level goal (e.g. "Get placed as an AI \
Engineer" or "Ship a portfolio website"). Break it down into a concrete, \
ordered project plan.

Return ONLY a JSON object with this exact shape, nothing else:
{
  "project_name": string (short, max ~8 words),
  "project_description": string or null (one or two sentences),
  "tasks": [
    {
      "order": integer (1-based, the sequence tasks should be tackled in),
      "title": string (short, action-oriented, max ~15 words),
      "description": string or null,
      "importance": one of "low", "medium", "high", "critical",
      "estimated_hours": a number or null (a reasonable rough guess is fine \
here -- this is a planning estimate, not a promise),
      "deadline_offset_days": integer or null (suggested number of days \
from now this task should be done by, to keep the goal on track; null if \
no reasonable timeline can be inferred)
    }
  ]
}

Rules:
- Produce 5-12 tasks: enough to be a real roadmap, not a single vague step, \
but not so granular it turns into a subtask list.
- Order tasks in the sequence they should actually be tackled \
(dependencies first).
- Keep deadline_offset_days internally consistent -- later tasks should \
generally have larger offsets than earlier ones.
- Do not add commentary, markdown, or any text outside the JSON object.
"""


def build_goal_breakdown_prompt(goal_text: str) -> str:
    """User-turn prompt for the Goal Breakdown agent."""
    return f'Goal:\n"""\n{goal_text.strip()}\n"""'


# --- Weekly Review (Reflection Agent) --------------------------------------

WEEKLY_REVIEW_SYSTEM = """You are the Reflection Agent inside a personal AI operating system.

You will be given a JSON summary of the user's last 7 days of work: hours \
worked, tasks completed vs planned, their most and least productive days, \
which task category they most underestimated (and by how much), and \
progress per project. Your only job is to write ONE short, direct, \
second-person recommendation sentence (max ~30 words) they can act on \
next week.

Rules:
- Base the recommendation only on the data given -- do not invent numbers.
- Prefer the single most actionable insight over a generic summary \
("start earlier", "protect your peak hours", "revisit the deadline"), \
not a restatement of the stats.
- Plain text only. No JSON, no markdown, no preamble like "Here's my \
recommendation:" -- just the sentence itself.
- If the data shows a strong week with no clear problem, write an \
encouraging one-sentence observation instead of manufacturing a critique.
"""


def build_weekly_review_prompt(stats_json: str) -> str:
    """User-turn prompt for the Weekly Review / Reflection agent."""
    return f"This week's stats:\n{stats_json}"
