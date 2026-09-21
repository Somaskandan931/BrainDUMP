"""
core/request_logging.py — one structured JSON log line per HTTP request,
plus a request_id every log line emitted while handling that request
inherits automatically (see logging_config.py's ContextVars).

This is the "structured logs" half of the production-readiness review's
observability item; core/sentry.py is the "error monitoring" half.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.core.logging_config import bind_request_context, clear_request_context

logger = logging.getLogger("app.request")

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns each request a request_id (reusing an inbound X-Request-ID
    if the client/load balancer already set one, so a request can be
    traced end-to-end across proxies), binds it to the logging context for
    the duration of the request, and logs one line with method, path,
    status, and duration once the response is ready.

    request.state.user_id is set later by api/deps.py's get_current_user
    (auth hasn't run yet at the point this middleware's "before" half
    executes) -- read here, after the handler returns, so an authenticated
    request's log line still carries user_id even though it wasn't known
    up front.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        bind_request_context(request_id)

        start = time.perf_counter()
        status_code = 500
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            user_id = getattr(request.state, "user_id", None)
            logger.info(
                "%s %s -> %d (%sms)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "user_id": user_id,
                    "client_ip": request.client.host if request.client else None,
                },
            )
            if response is not None:
                response.headers[_REQUEST_ID_HEADER] = request_id
            clear_request_context()
