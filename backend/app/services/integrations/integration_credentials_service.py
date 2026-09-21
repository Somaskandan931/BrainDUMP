"""
services/integration_credentials_service.py — per-user storage for
third-party integration credentials.

Multi-user auth follow-up: Google Calendar used to read one process-wide
token.json. Each user now connects their own Google account, and what that
produces has to live somewhere per-user: the `Credentials.to_json()` blob
(access token + refresh token + client info) from
integrations/google_calendar.exchange_code().

It is stored on the existing tenant-scoped `Setting` key-value table
(user_id + key is already unique, and database.py's tenant filter applies
to it automatically), so no new model or migration is needed. The value is
encrypted at rest with Fernet when config.INTEGRATION_ENCRYPTION_KEY is
set, and stored as plaintext otherwise (local dev only -- a warning is
logged once). Encrypted values carry an "enc:" prefix so plaintext rows
written before a key was configured still read back correctly.

Every function takes a live, tenant-scoped Session and commits its own
work, same convention as the rest of services/. Reads never raise on a
missing/undecryptable value -- they return None, which callers treat as
"this user hasn't connected that integration".
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.db.database import owner_id
from backend.app.models.settings import Setting

logger = logging.getLogger(__name__)

_GOOGLE_KEY = "integration_google_credentials"

_ENC_PREFIX = "enc:"
_warned_plaintext = False


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _fernet():
    """A Fernet built from config.INTEGRATION_ENCRYPTION_KEY, or None if unset/invalid."""
    if not config.INTEGRATION_ENCRYPTION_KEY:
        return None
    from cryptography.fernet import Fernet

    try:
        return Fernet(config.INTEGRATION_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        logger.error("INTEGRATION_ENCRYPTION_KEY is not a valid Fernet key (%s); storing plaintext", exc)
        return None


def _encode(plain: str) -> str:
    global _warned_plaintext
    f = _fernet()
    if f is None:
        if not _warned_plaintext:
            logger.warning(
                "INTEGRATION_ENCRYPTION_KEY is not set: integration tokens are being stored unencrypted."
            )
            _warned_plaintext = True
        return plain
    return _ENC_PREFIX + f.encrypt(plain.encode()).decode()


def _decode(stored: Optional[str]) -> Optional[str]:
    if not stored:
        return None
    if not stored.startswith(_ENC_PREFIX):
        return stored
    f = _fernet()
    if f is None:
        logger.error("Encrypted integration token found but INTEGRATION_ENCRYPTION_KEY is unset/invalid")
        return None
    from cryptography.fernet import InvalidToken

    try:
        return f.decrypt(stored[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        logger.error("Could not decrypt an integration token (wrong INTEGRATION_ENCRYPTION_KEY?)")
        return None


# ---------------------------------------------------------------------------
# Generic per-user get/set/delete on the Setting table
# ---------------------------------------------------------------------------

def _get(db: Session, key: str) -> Optional[str]:
    row = db.query(Setting).filter(Setting.key == key).first()
    return _decode(row.value) if row is not None else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    encoded = _encode(value)
    if row is None:
        db.add(Setting(user_id=owner_id(db), key=key, value=encoded))
    else:
        row.value = encoded
    db.commit()


def _delete(db: Session, key: str) -> bool:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------

def get_google_credentials_json(db: Session) -> Optional[str]:
    return _get(db, _GOOGLE_KEY)


def save_google_credentials_json(db: Session, credentials_json: str) -> None:
    _set(db, _GOOGLE_KEY, credentials_json)


def clear_google_credentials(db: Session) -> bool:
    return _delete(db, _GOOGLE_KEY)


def has_google_credentials(db: Session) -> bool:
    return get_google_credentials_json(db) is not None
