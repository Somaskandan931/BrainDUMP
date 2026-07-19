"""
app.py — FastAPI application entrypoint.

Registers every router, enables CORS for the local Next.js frontend,
initializes the database on startup, and (Milestone 5) starts the
APScheduler background jobs that run the morning plan and nightly
replan. Business logic never lives here — this file only wires things
together.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.database import init_db
from backend.api import projects, tasks, planner, analytics, calendar
from backend.scheduler.morning import run_morning_job
from backend.scheduler.nightly import run_nightly_job

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    _scheduler.add_job(
        run_morning_job,
        CronTrigger(hour=config.MORNING_JOB_HOUR, minute=0),
        id="morning_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_nightly_job,
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
    version="0.8.0",  # tracks milestone progress loosely
    lifespan=lifespan,
)

# Local Next.js dev server only — single-user, local-first app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(planner.router, prefix="/api/planner", tags=["planner"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    return {"status": "ok"}
