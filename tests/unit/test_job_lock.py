"""
jobs/distributed_lock.py — prevents the morning/nightly APScheduler jobs
from double-firing when more than one API instance is running (see
main.py's _locked_morning_job/_locked_nightly_job and that module's
docstring).
"""

from __future__ import annotations

import fakeredis
import pytest

from backend.app.jobs import distributed_lock
from backend.app.jobs.distributed_lock import job_lock


def test_job_lock_always_runs_when_redis_url_unset(monkeypatch):
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "", raising=False)
    with job_lock("morning_job") as should_run:
        assert should_run is True


def test_job_lock_runs_locally_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://unreachable:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: None)
    with job_lock("morning_job") as should_run:
        assert should_run is True


def test_job_lock_first_instance_claims_it(monkeypatch):
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: fake)

    with job_lock("morning_job") as should_run:
        assert should_run is True


def test_job_lock_second_instance_in_same_bucket_is_skipped(monkeypatch):
    # Simulates two API instances whose cron triggers fire within the same
    # time bucket -- the second must not also run the job.
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: fake)

    with job_lock("morning_job") as first_should_run:
        assert first_should_run is True

    with job_lock("morning_job") as second_should_run:
        assert second_should_run is False


def test_job_lock_different_jobs_dont_collide(monkeypatch):
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: fake)

    with job_lock("morning_job") as morning_should_run:
        assert morning_should_run is True
    with job_lock("nightly_job") as nightly_should_run:
        assert nightly_should_run is True


def test_job_lock_sets_a_ttl_past_the_bucket(monkeypatch):
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: fake)

    with job_lock("morning_job", bucket_seconds=3600) as should_run:
        assert should_run is True

    keys = fake.keys(f"{distributed_lock._LOCK_PREFIX}morning_job:*")
    assert len(keys) == 1
    ttl = fake.ttl(keys[0])
    assert 3600 < ttl <= 3720


def test_job_lock_new_bucket_allows_a_new_run(monkeypatch):
    # A later time bucket (next scheduled run, e.g. the next day) is a
    # fresh key -- yesterday's lock shouldn't block today's run.
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(distributed_lock.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(distributed_lock, "get_redis_client", lambda: fake)

    with job_lock("nightly_job", bucket_seconds=1) as first:
        assert first is True
    fake.flushall()  # stand-in for "an hour later, a new bucket"
    with job_lock("nightly_job", bucket_seconds=1) as second:
        assert second is True
