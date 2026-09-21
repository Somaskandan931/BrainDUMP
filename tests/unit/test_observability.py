"""
Structured logging (core/logging_config.py, core/request_logging.py) and
optional Sentry init (core/sentry.py).
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from backend.app.core import sentry as sentry_module
from backend.app.core.logging_config import (
    JsonFormatter,
    bind_request_context,
    clear_request_context,
)


@pytest.fixture(autouse=True)
def _clear_context():
    clear_request_context()
    yield
    clear_request_context()


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _make_record(msg: str = "hello", extra: dict | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_core_fields():
    payload = _format(_make_record("something happened"))
    assert payload["message"] == "something happened"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert "timestamp" in payload


def test_json_formatter_includes_bound_request_id_and_user_id():
    bind_request_context("req-123", user_id=42)
    payload = _format(_make_record())
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == 42


def test_json_formatter_omits_request_context_when_unbound():
    payload = _format(_make_record())
    assert "request_id" not in payload
    assert "user_id" not in payload


def test_json_formatter_includes_extra_fields():
    payload = _format(_make_record(extra={"duration_ms": 12.5, "path": "/health"}))
    assert payload["duration_ms"] == 12.5
    assert payload["path"] == "/health"


def test_json_formatter_extra_overrides_bound_context():
    # request.state-derived user_id (passed via extra) must win over the
    # ContextVar value -- see logging_config.py's merge-order comment.
    bind_request_context("req-1", user_id=1)
    payload = _format(_make_record(extra={"user_id": 2}))
    assert payload["user_id"] == 2


def test_json_formatter_includes_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = _format(record)
    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_emits_json_lines_on_stdout(capsys):
    from backend.app.core.logging_config import configure_logging

    configure_logging()
    logging.getLogger("app.test").info("configured logging works")
    captured = capsys.readouterr()
    line = [l for l in captured.out.splitlines() if l.strip()][-1]
    payload = json.loads(line)
    assert payload["message"] == "configured logging works"


# ---------------------------------------------------------------------------
# Request-ID propagation through a real request (RequestLoggingMiddleware)
# ---------------------------------------------------------------------------


def test_request_gets_an_x_request_id_header(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")


def test_inbound_x_request_id_is_reused(client):
    resp = client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
    assert resp.headers["X-Request-ID"] == "caller-supplied-id"


def test_authenticated_request_logs_user_id(client, user, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/projects")
    records = [r for r in caplog.records if r.name == "app.request"]
    assert records, "expected a request-completion log line"
    assert getattr(records[-1], "user_id", None) == user.id


# ---------------------------------------------------------------------------
# Sentry init: no-op when unset, tolerant of failure when set
# ---------------------------------------------------------------------------


def test_init_sentry_is_noop_when_dsn_unset(monkeypatch):
    monkeypatch.setattr(sentry_module.config, "SENTRY_DSN", "", raising=False)
    assert sentry_module.init_sentry() is False


def test_init_sentry_returns_true_when_dsn_set_and_sdk_available(monkeypatch):
    monkeypatch.setattr(
        sentry_module.config, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1", raising=False
    )
    monkeypatch.setattr(sentry_module.config, "ENVIRONMENT", "test", raising=False)
    try:
        assert sentry_module.init_sentry() is True
    finally:
        # Tear the client back down so it doesn't try to flush queued
        # events against a fake DSN when the test process exits.
        import sentry_sdk

        client = sentry_sdk.get_client()
        if client is not None:
            client.close(timeout=0)


def test_init_sentry_does_not_raise_if_sdk_init_fails(monkeypatch):
    monkeypatch.setattr(
        sentry_module.config, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1", raising=False
    )

    import sentry_sdk

    def _boom(*args, **kwargs):
        raise RuntimeError("sentry misconfigured")

    monkeypatch.setattr(sentry_sdk, "init", _boom)
    assert sentry_module.init_sentry() is False
