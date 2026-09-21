"""
core/logging_config.py — structured (JSON) logging for the whole app.

configure_logging(), called once from main.py before the app is built,
replaces the default unconfigured root logger with one JSON-line-per-log
handler on stdout. Every `logging.getLogger(__name__).info(...)` call
anywhere in the codebase gets this format for free -- no per-module
changes needed.

Why JSON on stdout rather than a logging service SDK: this app deploys to
Render (see ARCHITECTURE.md), which already collects stdout and lets you
ship it to a log sink (Datadog, Logtail, Better Stack, etc.) from there.
JSON lines are the lowest-common-denominator format nearly every log
sink can parse without a vendor-specific handler, so this doesn't lock
the app into one.

core/request_logging.py's middleware calls `bind_request_context()` /
`clear_request_context()` around each request so every log line emitted
while handling it -- including ones from deep inside business-logic
code that has no idea a request is in flight -- automatically carries
that request's request_id (and user_id once auth has resolved it).
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# Request-scoped context, set by request_logging.py's middleware. A
# ContextVar (not a plain module-level dict) so concurrent requests handled
# by the same async worker never see each other's request_id/user_id --
# each gets its own isolated value per asyncio task.
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id_var: ContextVar[Optional[int]] = ContextVar("user_id", default=None)

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JsonFormatter(logging.Formatter):
    """Renders each LogRecord as one JSON line: timestamp, level, logger
    name, message, request_id/user_id (when set), exception info (when
    present), plus any `extra={...}` fields the call site passed --
    e.g. `logger.info("...", extra={"duration_ms": 42})`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = _request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        user_id = _user_id_var.get()
        if user_id is not None:
            payload["user_id"] = user_id

        # `extra={...}` from the call site is authoritative and always
        # wins over the ContextVar-derived request_id/user_id above --
        # ContextVars can occasionally fail to propagate across
        # Starlette's middleware/task boundary depending on version,
        # while a value read from request.state (as request_logging.py's
        # middleware does for user_id) doesn't have that failure mode.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Call once, at process startup, before anything else logs."""
    root = logging.getLogger()
    root.setLevel(level)
    # Replace rather than add -- calling this twice (e.g. once from
    # main.py, once from a test fixture) shouldn't duplicate every line.
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # These two are extremely chatty at INFO (one line per DB statement /
    # HTTP call) and would drown out application logs; leave them at
    # WARNING unless someone explicitly wants SQL/HTTP tracing.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def bind_request_context(request_id: str, user_id: Optional[int] = None) -> None:
    _request_id_var.set(request_id)
    _user_id_var.set(user_id)


def set_user_context(user_id: int) -> None:
    """Called once auth resolves mid-request (request_id is already bound
    from the start of the request, before we know who's calling)."""
    _user_id_var.set(user_id)


def clear_request_context() -> None:
    _request_id_var.set(None)
    _user_id_var.set(None)
