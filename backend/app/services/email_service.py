"""
services/email_service.py — outbound transactional email.

One job: get a verification link or a password-reset link in front of
the user. Nothing here is a general-purpose mailer.

Behavior:
- config.SMTP_HOST set  -> sends a real email over SMTP (STARTTLS on 587
  by default, implicit TLS if SMTP_USE_SSL).
- config.SMTP_HOST unset -> logs the subject + body + link at INFO level
  instead of raising. This is deliberate: registration and password reset
  must keep working on a laptop with no mail server configured (local
  dev, CI, a fresh clone) -- see AUTH_REFACTOR_STATUS.md and item 13 of
  the production-readiness pass (README's privacy story vs. what's
  actually deployed) for the same "don't let an optional dependency's
  absence break the core flow" principle.

Callers should treat send_email() as best-effort: a dev SMTP misconfig
should not turn "reset your password" into a 500. Failures are logged
and swallowed, not raised, so /password-reset/request keeps returning
200 either way (see api/v1/auth.py's docstring on why that route never
reveals whether an email is registered).
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from backend.app.core import config

logger = logging.getLogger("braindump.email")


def send_email(to: str, subject: str, body: str) -> bool:
    """Best-effort send. Returns True if a real send was attempted and
    didn't raise; False (with a log line) otherwise. Never raises."""
    if not config.SMTP_HOST:
        logger.info("EMAIL (no SMTP configured, logging instead of sending)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM_ADDRESS}>"
    msg["To"] = to
    msg.set_content(body)

    try:
        if config.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
                if config.SMTP_USER:
                    server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
                server.starttls()
                if config.SMTP_USER:
                    server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception:
        # Best-effort: a mail-provider outage shouldn't 500 an auth route.
        # The user can always hit "resend" / "forgot password" again.
        logger.exception("Failed to send email to %s (subject: %s)", to, subject)
        return False


def send_verification_email(to: str, token: str) -> bool:
    link = f"{config.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    body = (
        "Welcome to BrainDUMP!\n\n"
        "Confirm your email address to activate your account:\n\n"
        f"{link}\n\n"
        f"This link expires in {config.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES} minutes. "
        "If you didn't create a BrainDUMP account, you can ignore this email."
    )
    return send_email(to, "Verify your BrainDUMP email", body)


def send_password_reset_email(to: str, token: str) -> bool:
    link = f"{config.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    body = (
        "We received a request to reset your BrainDUMP password.\n\n"
        f"{link}\n\n"
        f"This link expires in {config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. "
        "If you didn't request this, you can ignore this email -- your password won't change."
    )
    return send_email(to, "Reset your BrainDUMP password", body)
