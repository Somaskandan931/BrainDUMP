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
# backend/config.py moves to backend/app/core/config.py as part of the
# backend/app domain restructure, so this now climbs four levels
# (core -> app -> backend -> repo root) instead of the original one.
BASE_DIR = Path(__file__).resolve().parents[3]              # repo root
# BRAINDUMP_DATA_DIR lets the test suite (tests/conftest.py) point the whole
# app at a throwaway directory instead of the real data/tasks.db.
DATA_DIR = Path(os.getenv("BRAINDUMP_DATA_DIR", BASE_DIR / "data"))
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Database (Milestone 2; Postgres-ready as of the multi-user SaaS pass)
# ---------------------------------------------------------------------------
# SQLite remains the local-dev / single-instance default -- zero setup, one
# file. Set DATABASE_URL (e.g. postgresql+psycopg://user:pass@host/db) for
# any deployment with more than one API/worker process: SQLite's file lock
# does not hold up under concurrent writers (API + APScheduler/worker jobs
# + multiple instances), which is the multi-user failure mode described in
# ARCHITECTURE.md. No code above the engine cares which one is active.
DB_PATH = DATA_DIR / "tasks.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

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
# Kept for anything (old tests/scripts) that still calls create_access_token()
# with no explicit expiry. New code should use ACCESS_TOKEN_EXPIRE_MINUTES.
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days

# --- Session model: short-lived access token + HttpOnly-cookie refresh token ---
# Previously a single 7-day JWT was handed to the frontend and kept in
# localStorage indefinitely -- readable by any script on the page (XSS) and,
# if it leaked, valid for a week with no way to revoke it. Now the bearer
# token returned in the response body is short-lived, and a long-lived
# refresh token is stored server-side (models/refresh_token.py, hashed) and
# handed to the browser only as an HttpOnly cookie -- see auth/token_service.py
# and api/v1/auth.py's /refresh, /logout.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
REFRESH_COOKIE_NAME = "brain_dump_refresh"
# Scoped to /api/auth so the (still HttpOnly) cookie isn't attached to every
# other request -- only /refresh and /logout ever need to read it.
REFRESH_COOKIE_PATH = "/api/auth"
# Secure=False only makes sense for plain-http local dev; browsers silently
# drop a Secure cookie set over http. Default on (safe for any real deploy);
# set COOKIE_SECURE=false in a local .env if you are testing over http.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("false", "0", "")
# "lax" is enough here (the cookie is only ever sent on same-site navigations
# and same-site/simple cross-site fetches) and, unlike "strict", still
# attaches after an OAuth redirect back from Google/GitHub.
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

# Web application OAuth client id from Google Cloud Console — separate from
# whatever Web-application client GOOGLE_CALENDAR_CLIENT_ID below uses for
# Calendar sync. Used to verify the ID token Google Identity Services hands
# the frontend (see auth/google_login.py). Empty disables Google login.
GOOGLE_LOGIN_CLIENT_ID = os.getenv("GOOGLE_LOGIN_CLIENT_ID", "")

# GitHub OAuth app (GitHub -> Settings -> Developer settings -> OAuth
# Apps -> New OAuth App). Used for "Sign in with GitHub" -- see
# auth/github_login.py for why this is a code exchange rather than a
# verified-locally token like Google's. The redirect URI is a *frontend*
# route (app/auth/github/callback), not a backend one: GitHub redirects
# the browser there with `code`, and the frontend page is what POSTs
# that code to our own POST /api/auth/github. Empty disables GitHub login.
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URI = os.getenv(
    "GITHUB_OAUTH_REDIRECT_URI", "http://localhost:3000/auth/github/callback"
)

# Brute-force limits on /api/auth/* (auth/rate_limit.py; in-memory, per process).
# Login failures are counted per (client IP, email) and, more loosely, per client
# IP alone; registrations and Google sign-ins per client IP.
AUTH_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5"))
AUTH_LOGIN_IP_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_IP_MAX_FAILURES", "20"))
AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))  # 15 min
AUTH_REGISTER_MAX_PER_IP = int(os.getenv("AUTH_REGISTER_MAX_PER_IP", "10"))
AUTH_REGISTER_WINDOW_SECONDS = int(os.getenv("AUTH_REGISTER_WINDOW_SECONDS", "3600"))  # 1 hour

# ---------------------------------------------------------------------------
# AI / LLM (Milestone 4 — originally local Ollama; swapped to OpenRouter's
# hosted free tier so inference doesn't depend on a machine staying on and
# a tunnel running — see backend/ai/ollama_client.py)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# A ":free"-suffixed model slug. If OpenRouter retires this particular free
# model, swap it via the OPENROUTER_MODEL env var — no code change needed.
# Browse current free options at https://openrouter.ai/models?max_price=0
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

# Per-user daily cap on AI calls (brain dump, goal breakdown, weekly review
# recommendation, morning narration, coach fallback replies) -- see
# services/usage_service.py. 0 disables the check entirely (unlimited) --
# do not do this with a paid model key.
AI_DAILY_CALL_LIMIT = int(os.getenv("AI_DAILY_CALL_LIMIT", "50"))

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
# GET /metrics in Prometheus text format (main.py). On by default; disable
# per-instance if something else scrapes metrics a different way.
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").strip().lower() not in ("false", "0", "")

# ---------------------------------------------------------------------------
# Activity log / audit trail (services/workspace/activity_service.py)
# ---------------------------------------------------------------------------
# How long a user's activity_log rows are kept before the nightly job
# purges them (per user, not a global sweep). 0 keeps everything forever.
ACTIVITY_LOG_RETENTION_DAYS = int(os.getenv("ACTIVITY_LOG_RETENTION_DAYS", "180"))

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

# Run the morning/nightly APScheduler jobs in *this* process. Safe (and
# the simplest option) for a single instance -- the app's default. Once
# there is more than one API instance, every one of them would otherwise
# fire the same cron job at the same time (duplicate morning plans,
# duplicate replans) -- set this to false on every API instance and run
# the jobs from one dedicated `python -m backend.worker` process instead
# (see jobs/scheduler.py, worker.py).
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").strip().lower() not in ("false", "0", "")

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