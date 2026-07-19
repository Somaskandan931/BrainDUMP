"""
config.py — Centralized app configuration.

Milestone 2: real database paths wired up. Milestone 4: Ollama settings
wired up. Milestone 6: Calendar settings wired up (values now
come from a local .env — see .env at the repo root; nothing
secret is hardcoded or committed).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # loads ai_os/.env if present; no-op (and no error) otherwise

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # ai_os/
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Database (Milestone 2)
# ---------------------------------------------------------------------------
DB_PATH = DATA_DIR / "tasks.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Echo raw SQL to stdout — handy during development, noisy in normal use.
SQL_ECHO = False

# ---------------------------------------------------------------------------
# AI / Ollama (placeholder — filled in Milestone 4)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:8b"

# ---------------------------------------------------------------------------
# Calendar (Milestone 6)
# ---------------------------------------------------------------------------
# OAuth client secret downloaded from Google Cloud Console (Desktop app
# credential type). Never committed — see .env / INTEGRATIONS.md
# for the one-time setup steps.
GOOGLE_CREDENTIALS_PATH = BASE_DIR / "credentials.json"
# Written automatically on first successful OAuth flow; holds the refresh
# token so later runs never need the browser consent screen again.
GOOGLE_TOKEN_PATH = BASE_DIR / "token.json"
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# How far back "sync" also re-checks for stale/removed events, in addition
# to config.SCHEDULING_HORIZON_DAYS ahead (reused as-is for the forward
# window so there's one number, not two horizons that can drift apart).
CALENDAR_SYNC_LOOKBACK_DAYS = 1

# ---------------------------------------------------------------------------
# Scheduler / planning engine (Milestone 5)
# ---------------------------------------------------------------------------
MORNING_JOB_HOUR = 7
NIGHTLY_JOB_HOUR = 23

# Working hours the scheduler is allowed to pack tasks into. Naive local
# time for now — timezone handling is a later-milestone concern once
# Google Calendar (real timezone-aware events) lands in Milestone 6.
WORK_DAY_START_HOUR = 9
WORK_DAY_END_HOUR = 21

# How far ahead schedule_pending_tasks()/replan() look when packing tasks
# into free slots.
SCHEDULING_HORIZON_DAYS = 7

# Smallest block worth scheduling. Tasks (or remaining slot fragments)
# shorter than this are skipped rather than creating a 4-minute session.
MIN_SLOT_MINUTES = 15

# Fallback duration used when a task has no estimated_hours yet and the
# Estimator can't infer one either (see ml/estimator.py DEFAULT_HOURS_BY_IMPORTANCE).
DEFAULT_TASK_HOURS = 1.0

# --- Deadline Engine buffers (services/deadline_service.py) -----------------
# "When should I actually aim to be done" is a spectrum, not one date.
# Each level pulls the target completion date this many days before the
# real deadline. Aggressive = the deadline itself (0-day buffer).
DEADLINE_BUFFER_DAYS = {
    "safe": 2,
    "default": 1,
    "aggressive": 0,
}

# Feasibility thresholds, expressed as (free calendar hours before the
# target) / (hours of work still needed). >= SAFE ratio -> plenty of
# room; >= TIGHT ratio -> fits, but no slack; below TIGHT -> the math
# doesn't work at this buffer level without moving something else.
DEADLINE_SAFE_RATIO = 1.5
DEADLINE_TIGHT_RATIO = 1.0

# How far past the furthest buffer target to look for free slots, and
# the hard cap regardless of how far away the deadline is (a deadline
# months out shouldn't make this scan an unbounded window).
DEADLINE_PLAN_LOOKAHEAD_PADDING_DAYS = 3
DEADLINE_PLAN_MAX_HORIZON_DAYS = 60

# --- Priority Engine weights (ml/priority_model.py) -------------------------
# Hand-tuned weighted sum for Milestone 5. Milestone 8 replaces this with a
# learned model once enough "what the user actually worked on" data exists.
# All five components are normalized to roughly 0-1 before weighting, so
# these weights are directly comparable to each other.
PRIORITY_WEIGHTS = {
    "deadline_risk": 0.35,
    "importance": 0.25,
    "estimated_hours": 0.10,
    "context_switch_cost": 0.15,
    "energy_fit": 0.15,
}

# Context switching: a same-project task right after another task from that
# project costs ~0; a different project costs the full penalty (0-1 scale
# before weighting).
CONTEXT_SWITCH_SAME_PROJECT_COST = 0.0
CONTEXT_SWITCH_DIFFERENT_PROJECT_COST = 1.0
CONTEXT_SWITCH_NO_PROJECT_COST = 0.4

# Energy pattern: hour-of-day -> the EnergyLevel the user tends to have then.
# No per-user learning yet (that's Setting-backed personalization, a later
# milestone) — a reasonable default deep-work-in-the-morning curve for now.
DEFAULT_ENERGY_PATTERN = {
    **{h: "high" for h in range(6, 12)},
    **{h: "medium" for h in range(12, 17)},
    **{h: "low" for h in range(17, 22)},
    **{h: "low" for h in list(range(0, 6)) + [22, 23]},
}
