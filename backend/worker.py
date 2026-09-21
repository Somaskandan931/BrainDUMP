"""
backend/worker.py — standalone process for the morning/nightly cron jobs.

Run this as its own process (`python -m backend.worker`) once there is
more than one API instance, with ENABLE_SCHEDULER=false set on every API
instance -- see jobs/scheduler.py for why running the scheduler in every
API process stops being safe at that point (duplicate morning plans,
duplicate nightly replans). Exactly one worker process should run at a
time; nothing here coordinates multiple workers.

For a single-instance deployment (the default), you don't need this at
all -- leave ENABLE_SCHEDULER unset (defaults to true) and the API
process runs the jobs itself, same as before this split existed.
"""

from __future__ import annotations

import logging
import signal
import time

from backend.app.db.database import init_db
from backend.app.jobs.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backend.worker")

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.info("worker: received signal %s, shutting down", signum)
    _shutdown = True


def main() -> None:
    init_db()
    start_scheduler()
    logger.info("worker: scheduler running; Ctrl-C or SIGTERM to stop")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        while not _shutdown:
            time.sleep(1)
    finally:
        stop_scheduler()
        logger.info("worker: stopped")


if __name__ == "__main__":
    main()
