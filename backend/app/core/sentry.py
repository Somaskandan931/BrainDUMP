"""
core/sentry.py — optional error monitoring.

init_sentry(), called once from main.py before the FastAPI app is built,
turns on Sentry's exception capture + request context when
config.SENTRY_DSN is set. Left unset, this is a no-op -- exceptions still
show up in the structured stdout logs (core/logging_config.py) with a full
traceback, just without Sentry's grouping/alerting/breadcrumbs on top.

Deliberately tolerant of sentry-sdk itself being missing or failing to
import: it's declared in requirements.txt, but if a deployment trims it
out (or an old version chokes on the fastapi integration), that shouldn't
be able to crash app startup -- error *monitoring* going down is not a
reason to take the whole app down with it.
"""

from __future__ import annotations

import logging

from backend.app.core import config

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Returns True if Sentry was actually initialized."""
    if not config.SENTRY_DSN:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        # Sentry's own logging integration mirrors ERROR+ log records into
        # Sentry as events automatically -- so `logger.exception(...)`
        # anywhere in the app (the morning/nightly jobs already do this
        # per-user, see jobs/tasks/morning_plan.py) reaches Sentry with no
        # extra call needed at each site. breadcrumb_level=INFO means INFO
        # and above show up as breadcrumbs leading up to whatever error
        # triggered the event, for context.
        logging_integration = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)

        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            environment=config.ENVIRONMENT,
            integrations=[FastApiIntegration(), StarletteIntegration(), logging_integration],
            traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
            # Request bodies can contain passwords (login/register) and
            # OAuth codes (Google/GitHub sign-in) -- never send them.
            send_default_pii=False,
        )
        return True
    except Exception:
        logger.exception("SENTRY_DSN is set but Sentry failed to initialize; continuing without it.")
        return False
