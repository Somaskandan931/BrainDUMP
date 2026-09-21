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
# BRAINDUMP_DATA_DIR lets the test suite (tests/conftest.py) point the whole
# app at a throwaway directory instead of the real data/tasks.db.
DATA_DIR = Path(os.getenv("BRAINDUMP_DATA_DIR", BASE_DIR / "data"))
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
# Auth (multi-user)
# ---------------------------------------------------------------------------
# HMAC secret JWTs are signed with. Must be set in .env for anything beyond
# local dev — a default is provided only so the app boots without one, not
# because it's safe to run with it.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days

# Web application OAuth client id from Google Cloud Console — separate from
# whatever Web-application client GOOGLE_CALENDAR_CLIENT_ID below uses for
# Calendar sync. Used to verify the ID token Google Identity Services hands
# the frontend (see auth/google_login.py). Empty disables Google login.
GOOGLE_LOGIN_CLIENT_ID = os.getenv("GOOGLE_LOGIN_CLIENT_ID", "")

# Brute-force limits on /api/auth/* (auth/rate_limit.py; in-memory, per process).
# Login failures are counted per (client IP, email) and, more loosely, per client
# IP alone; registrations and Google sign-ins per client IP.
AUTH_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5"))
AUTH_LOGIN_IP_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_IP_MAX_FAILURES", "20"))
AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))  # 15 min
AUTH_REGISTER_MAX_PER_IP = int(os.getenv("AUTH_REGISTER_MAX_PER_IP", "10"))
AUTH_REGISTER_WINDOW_SECONDS = int(os.getenv("AUTH_REGISTER_WINDOW_SECONDS", "3600"))  # 1 hour

# ---------------------------------------------------------------------------
# AI / Ollama (placeholder — filled in Milestone 4)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:8b"

# ---------------------------------------------------------------------------
# Calendar (Milestone 6; per-user OAuth as of the multi-user auth refactor)
# ---------------------------------------------------------------------------
# Web application OAuth client (Google Cloud Console -> Credentials ->
# Create Credentials -> OAuth client ID -> Web application). Separate from
# GOOGLE_LOGIN_CLIENT_ID above -- that one only verifies Google Sign-In ID
# tokens; this one is a full OAuth client with a secret, used to request
# offline (refresh-token-bearing) Calendar access for whichever user
# connects their calendar from Settings. Empty disables the feature (every
# calendar endpoint 424s with setup instructions, same as before).
GOOGLE_CALENDAR_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
# Must exactly match a redirect URI registered on that OAuth client, and
# point at api/calendar.py's GET /google/callback route.
GOOGLE_CALENDAR_REDIRECT_URI = os.getenv(
    "GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost:8000/api/calendar/google/callback"
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Where the OAuth callback sends the browser once it's done (it appends
# ?calendar=connected or ?calendar=error). The callback is hit by Google's
# redirect, not by the SPA, so it has to bounce the user back explicitly.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Fernet key used to encrypt each user's stored Google refresh token at
# rest (services/integration_credentials_service.py).
# Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Unset = tokens are stored as plaintext in the settings table (fine for a
# throwaway local dev DB; set it for anything real).
INTEGRATION_ENCRYPTION_KEY = os.getenv("INTEGRATION_ENCRYPTION_KEY", "")

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

# --- Scheduler Rules 3/4/6 (PRD §20 "Scheduling Rules" / §65) ---------------
# Lunch is carved out of every working day the same way a meeting would be
# (Rule 3: "Protect lunch"), and a break is inserted once a contiguous run
# of packed work reaches BREAK_AFTER_MINUTES (Rule 4/6: "Protect breaks" /
# "Insert 15-minute break after 90 minutes").
LUNCH_START_HOUR = 13
LUNCH_END_HOUR = 14
BREAK_AFTER_MINUTES = 90
BREAK_DURATION_MINUTES = 15

# Smallest block worth scheduling. Tasks (or remaining slot fragments)
# shorter than this are skipped rather than creating a 4-minute session.
MIN_SLOT_MINUTES = 15

# Fallback duration used when a task has no estimated_hours yet and the
# Estimator can't infer one either (see ml/estimator.py DEFAULT_HOURS_BY_IMPORTANCE).
DEFAULT_TASK_HOURS = 1.0

# --- Scheduler Rule 9 (PRD §20 "Group similar work together") ---------------
# Tasks lack any explicit category/label field (see ai/long_term_memory.py's
# note on why "frequently used labels" was dropped from that profile for the
# same reason) -- project_id is the only real "kind of work" signal in this
# schema, so clustering groups same-project tasks adjacently in the packing
# order. Only applied within priority ties this close together, so
# clustering only ever reorders noise-level ties, never lets "group similar
# work" override a genuinely higher-priority task from a different project.
CLUSTER_PRIORITY_TOLERANCE = 0.05

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