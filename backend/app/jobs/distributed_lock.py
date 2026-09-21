"""
jobs/distributed_lock.py — Redis-based leader lock so only one API instance
actually executes a scheduled job's body when APScheduler is running
independently inside every instance (see main.py's lifespan).

Every instance still runs its own BackgroundScheduler, and every instance's
cron trigger fires at the same wall-clock time -- that part isn't changed
here. A real fix is moving cron execution out of the API process entirely
into a separate worker process (see ARCHITECTURE.md's P1 note on this),
which is a bigger infra change (a job queue, a worker deployment target)
than the current single-Render-service setup warrants yet. What this adds
is a cheap race at the moment each trigger fires: whichever instance gets
there first claims a Redis lock for that job name + time bucket with
`SET NX EX`; every other instance sees the lock already held and skips its
run instead of also executing the job, logging that it did so.

The lock key is scoped to a time bucket (default: the current hour) rather
than a single instant, so instances whose clocks/trigger firing are a few
seconds apart still collide on the same key. The lock's TTL is the bucket
size plus a little slack, so a job that runs long or a process that
crashes mid-job doesn't wedge anything -- it just expires before the next
scheduled fire (the next occurrence is a day away for morning/nightly, so
an hour-long bucket has no risk of blocking tomorrow's run).

No REDIS_URL configured => there's nothing to coordinate with (single
instance) or the deployer has accepted the duplicate-run risk, so
job_lock() always proceeds -- exactly today's behavior, unchanged. Same
choice if REDIS_URL is set but Redis is unreachable: run the job locally
rather than let a Redis hiccup silently skip every instance's scheduled
run (see core/redis_client.py's docstring for the same reasoning applied
to rate limiting).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from backend.app.core import config
from backend.app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "joblock:"


def _time_bucket(now: datetime, bucket_seconds: int) -> int:
    epoch = int(now.timestamp())
    return epoch - (epoch % bucket_seconds)


@contextmanager
def job_lock(job_name: str, bucket_seconds: int = 3600) -> Iterator[bool]:
    """Context manager yielding True if this process should run `job_name`
    right now, False if another instance already claimed it for this time
    bucket. Callers must skip the job body entirely when it yields False.

    Usage:
        with job_lock("morning_job") as should_run:
            if should_run:
                run_morning_job()
    """
    if not config.REDIS_URL:
        yield True
        return

    client = get_redis_client()
    if client is None:
        logger.warning(
            "job_lock: REDIS_URL is set but Redis is unreachable; running "
            "%s locally without cross-instance coordination.",
            job_name,
        )
        yield True
        return

    now = datetime.now(timezone.utc)
    bucket = _time_bucket(now, bucket_seconds)
    key = f"{_LOCK_PREFIX}{job_name}:{bucket}"
    ttl = bucket_seconds + 120
    acquired = bool(client.set(key, "1", nx=True, ex=ttl))
    if not acquired:
        logger.info(
            "job_lock: %s already claimed by another instance for this run; skipping.",
            job_name,
        )
    yield acquired
