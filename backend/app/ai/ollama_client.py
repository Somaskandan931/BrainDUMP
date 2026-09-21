"""
ai/ollama_client.py — Thin wrapper over OpenRouter's chat-completions API.

Originally a wrapper around a local Ollama daemon. Swapped to OpenRouter's
hosted free tier so inference doesn't depend on any machine staying on or
a tunnel being alive: every agent (task_parser, planner_service,
analytics_service, ai_coach_service, scheduler/morning.py) already goes
through call_model() / call_model_json() here instead of hitting a
provider directly, so this was a transport-only change — the public
functions, their signatures, and the OllamaError type are all unchanged,
and none of those callers needed to change.

The module name and OllamaError's name are kept as-is (rather than
renamed to something OpenRouter-specific) purely to avoid a mechanical
rename across every file that does `from backend.app.ai.ollama_client import
OllamaError, call_model`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import requests
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.services.ai import usage_service

logger = logging.getLogger(__name__)

_CHAT_COMPLETIONS_URL = f"{config.OPENROUTER_BASE_URL}/chat/completions"


class OllamaError(RuntimeError):
    """
    Raised for both transport failures (no API key, network error, rate
    limit, timeout after retries) and content failures (model didn't
    return valid JSON when json_mode was requested). Callers generally
    treat both the same way -- surface a 502-ish "AI backend unavailable
    or misbehaved" to the API layer -- so one error type keeps their
    except clauses simple.
    """


def _headers() -> dict[str, str]:
    if not config.OPENROUTER_API_KEY:
        raise OllamaError(
            "OPENROUTER_API_KEY is not set. Get a free key at "
            "https://openrouter.ai/keys and set it as an env var."
        )
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/brain-dump",
        "X-Title": "Brain Dump",
    }


def call_model(
    prompt: str,
    system: Optional[str] = None,
    *,
    model: Optional[str] = None,
    json_mode: bool = True,
    temperature: float = 0.2,
    max_retries: int = 2,
    retry_backoff_seconds: float = 1.5,
    db: Optional[Session] = None,
) -> str:
    """
    Send a single prompt (+ optional system prompt) to the configured
    OpenRouter model and return the raw text of the response.

    Retries only transport-level failures (network error, timeout, rate
    limit) -- not malformed model output, since retrying a bad prompt with
    the same prompt just wastes a call against the free-tier quota. That
    distinction lives in call_model_json(), which is where malformed JSON
    actually surfaces.

    `db`, when passed, scopes this call to a user's daily AI usage cap: the
    caller's user_id is read from db.info["user_id"] (the same key
    api.deps.get_scoped_db / background jobs set for tenant filtering),
    checked against config.AI_DAILY_CALL_LIMIT via services.usage_service
    *before* the request goes out. Omitting `db` skips usage tracking.
    """
    user_id = db.info.get("user_id") if db is not None else None
    if user_id is not None:
        usage_service.enforce_limit(db, user_id)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model or config.OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                _CHAT_COMPLETIONS_URL,
                headers=_headers(),
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise OllamaError(f"OpenRouter returned an error: {data['error']}")

            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - network/HTTP/JSON errors all land here
            last_error = exc
            logger.warning(
                "OpenRouter call failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * (attempt + 1))

    raise OllamaError(
        f"Could not get a response from OpenRouter ({config.OPENROUTER_MODEL}) "
        f"after {max_retries + 1} attempt(s): {last_error}"
    ) from last_error


def call_model_json(
    prompt: str,
    system: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """
    Like call_model(), but parses the response as JSON and raises
    OllamaError (not json.JSONDecodeError) on invalid JSON, so every
    caller can catch one exception type regardless of whether OpenRouter
    was unreachable or just returned garbage.
    """
    raw = call_model(prompt, system=system, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError(
            f"Model did not return valid JSON: {exc}. Raw output (truncated): {raw[:500]!r}"
        ) from exc
