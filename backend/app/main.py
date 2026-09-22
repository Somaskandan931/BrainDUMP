"""
app.py — FastAPI application entrypoint.

Registers every router, enables CORS for the local Next.js frontend,
initializes the database on startup, and starts the APScheduler
background jobs that run the morning plan and nightly replan.
Business logic never lives here — this file only wires things together.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core import config
from backend.app.core.request_logging import RequestLoggingMiddleware
from backend.app.db.database import init_db
from backend.app.api.v1 import (
    activity,
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
)
from backend.app.jobs.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # config.ENABLE_SCHEDULER lets the morning/nightly cron jobs be run by a
    # single dedicated process (`python -m backend.worker`) instead of every
    # API instance -- see jobs/scheduler.py's module docstring for why
    # running them in-process stops being safe once there's more than one
    # API instance (duplicate morning plans, duplicate replans).
    if config.ENABLE_SCHEDULER:
        start_scheduler()

    yield

    if config.ENABLE_SCHEDULER:
        stop_scheduler()


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

# Assigns/echoes X-Request-ID and logs one structured line per request
# (see core/request_logging.py). Was previously defined but never
# registered, so requests carried no request_id and authenticated calls
# weren't attributed to a user in the logs.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
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

if config.ENABLE_METRICS:
    # Exposes GET /metrics in Prometheus text format: request counts,
    # latency histograms, and in-progress requests, labeled by method/
    # path/status. No custom business metrics yet (AI latency, queue
    # depth, jobs failed) -- those live in jobs/scheduler.py and
    # services/ai/usage_service.py once there's a scrape target to send
    # them to; this wires up the baseline HTTP-level observability first.
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok"}
