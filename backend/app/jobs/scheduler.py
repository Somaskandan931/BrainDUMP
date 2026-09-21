"""
jobs/scheduler.py — the morning/nightly cron jobs, extracted so they can
run either in-process (the API, when config.ENABLE_SCHEDULER is true --
the single-instance default) or as their own process (`python -m
backend.worker`, for a deployment with more than one API instance).

Why this had to move out of app/main.py: APScheduler's BackgroundScheduler
runs inside whatever process constructs it. With more than one API
instance behind a load balancer, each instance used to construct its own
scheduler and each one would fire run_morning_job/run_nightly_job at the
same cron tick -- N morning plans and N nightly replans instead of one.
There is nothing in this file that de-duplicates across processes; the
fix is topological (config.ENABLE_SCHEDULER=false on every API instance,
exactly one `python -m backend.worker` process), not a lock in here.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core import config
from backend.app.jobs.tasks.morning_plan import run_morning_job
from backend.app.jobs.tasks.nightly_replan import run_nightly_job

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_morning_job,
        CronTrigger(hour=config.MORNING_JOB_HOUR, minute=0),
        id="morning_job",
        replace_existing=True,
    )
    scheduler.add_job(
        run_nightly_job,
        CronTrigger(hour=config.NIGHTLY_JOB_HOUR, minute=0),
        id="nightly_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler: started (morning=%02d:00, nightly=%02d:00)", config.MORNING_JOB_HOUR, config.NIGHTLY_JOB_HOUR)
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
