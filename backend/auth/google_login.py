"""
auth/google_login.py — verifies a Google ID token server-side.

The frontend uses Google Identity Services (see
frontend/components/auth/GoogleButton.tsx) to get an ID token directly
from Google in the browser, and sends *only that token* to
POST /api/auth/google. We never trust the browser's word for who the
user is — google.oauth2.id_token.verify_oauth2_token re-verifies the
token's signature against Google's public keys and checks it was
issued for our own OAuth client id (GOOGLE_LOGIN_CLIENT_ID), which is
what stops a token minted for a different app from being replayed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from backend import config


@dataclass
class GoogleProfile:
    sub: str
    email: str
    name: str | None
    picture: str | None


def verify_google_id_token(token: str) -> GoogleProfile | None:
    """Returns the verified profile, or None if the token is invalid,
    expired, or wasn't issued for our client id."""
    if not config.GOOGLE_LOGIN_CLIENT_ID:
        return None
    try:
        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), config.GOOGLE_LOGIN_CLIENT_ID
        )
    except ValueError:
        return None

    if not claims.get("email_verified", False):
        return None

    return GoogleProfile(
        sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
