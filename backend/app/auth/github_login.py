"""
auth/github_login.py — exchanges a GitHub OAuth authorization code for a
verified profile, server-side.

Unlike Google Identity Services (which hands the frontend a signed ID
token it can verify locally), GitHub's OAuth flow is the classic
Authorization Code grant: the frontend sends the user's browser to
GitHub's consent screen, GitHub redirects back to our frontend with a
one-time `code`, and only the backend -- holding GITHUB_CLIENT_SECRET,
which must never reach the browser -- can exchange that code for an
access token. This module owns exactly that exchange plus the two
follow-up GitHub API calls needed to get a verified email (GitHub's
`/user` endpoint omits email entirely for accounts that keep it
private, so `/user/emails` is the only reliable source).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from backend.app.core import config


@dataclass
class GithubProfile:
    sub: str  # GitHub's numeric account id, as a string (stable; login/email can both change)
    email: str
    name: Optional[str]
    avatar_url: Optional[str]


def exchange_code_for_profile(code: str) -> Optional[GithubProfile]:
    """Returns the verified profile, or None if the code is invalid/expired,
    the exchange fails, or the account has no verified email GitHub will
    hand back (rare, but an unverified-only email isn't good enough to
    trust as this account's identity)."""
    if not (config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET):
        return None

    try:
        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": config.GITHUB_OAUTH_REDIRECT_URI,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return None

        auth_header = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}

        user_resp = requests.get("https://api.github.com/user", headers=auth_header, timeout=10)
        user_resp.raise_for_status()
        profile = user_resp.json()

        email = profile.get("email")
        if not email:
            # Private-email accounts need the dedicated endpoint; pick the
            # primary verified address, same as GitHub's own "Sign in
            # with GitHub" reference implementations do.
            emails_resp = requests.get(
                "https://api.github.com/user/emails", headers=auth_header, timeout=10
            )
            emails_resp.raise_for_status()
            verified_primary = next(
                (e["email"] for e in emails_resp.json() if e.get("primary") and e.get("verified")),
                None,
            )
            email = verified_primary or next(
                (e["email"] for e in emails_resp.json() if e.get("verified")), None
            )

        if not email:
            return None

        return GithubProfile(
            sub=str(profile["id"]),
            email=email,
            name=profile.get("name") or profile.get("login"),
            avatar_url=profile.get("avatar_url"),
        )
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None
