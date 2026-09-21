"""
app.py — FastAPI application entrypoint.

Registers every router, enables CORS for the local Next.js frontend,
initializes the database on startup, and starts the APScheduler
background jobs that run the morning plan and nightly replan.
Business logic never lives here — this file only wires things together.

Logging/monitoring are configured first, before anything else runs, so
even a startup failure below this point gets a structured log line and
(if configured) a Sentry event instead of a bare traceback on stderr.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.logging_config import configure_logging

configure_logging()

from backend.app.core import config
from backend.app.core.request_logging import RequestLoggingMiddleware
from backend.app.core.sentry import init_sentry
from backend.app.db.database import init_db
from backend.app.jobs.distributed_lock import job_lock
from backend.app.api.v1 import (
    auth,
    projects,
    tasks,
    planner,
    analytics,
    calendar,
    notifications,
    chat,
    memory,
    schedule,
    settings as settings_api,
    demo,
    activity,
)
from backend.app.jobs.tasks.morning_plan import run_morning_job
from backend.app.jobs.tasks.nightly_replan import run_nightly_job

init_sentry()

_scheduler = BackgroundScheduler()


def _locked_morning_job() -> None:
    """APScheduler entry point. Wraps run_morning_job() in the Redis lock
    from jobs/distributed_lock.py so, when REDIS_URL is set and this
    service is running as more than one instance, only one instance's
    7 AM trigger actually runs the job -- see that module's docstring."""
    with job_lock("morning_job") as should_run:
        if should_run:
            run_morning_job()


def _locked_nightly_job() -> None:
    """Same as _locked_morning_job() above, for the 11 PM nightly replan."""
    with job_lock("nightly_job") as should_run:
        if should_run:
            run_nightly_job()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    _scheduler.add_job(
        _locked_morning_job,
        CronTrigger(hour=config.MORNING_JOB_HOUR, minute=0),
        id="morning_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        _locked_nightly_job,
        CronTrigger(hour=config.NIGHTLY_JOB_HOUR, minute=0),
        id="nightly_job",
        replace_existing=True,
    )
    _scheduler.start()

    yield

    _scheduler.shutdown(wait=False)


app = FastAPI(
    title="Brain Dump — Personal AI OS",
    description="Local-first AI planning system. See ARCHITECTURE.md.",
    version="0.9.0",  # tracks milestone progress loosely
    lifespan=lifespan,
)

# Multi-user now, but still deployable as a single local instance -- the
# allowed origin(s) come from ALLOWED_ORIGINS (comma-separated) instead of
# being hardcoded, defaulting to the local Next.js dev server when unset.
_allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Runs for every request; logged first (outermost) so its timing covers
# CORS/auth/everything downstream, not just the route handler.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(planner.router, prefix="/api/planner", tags=["planner"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(demo.router, prefix="/api/demo", tags=["demo"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok"}
