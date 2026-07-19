"""
ai/ollama_client.py — Thin wrapper around the local Ollama Python client.

Every agent (task_parser, planner_service, and later milestones' scheduler/
priority/weekly-review agents) goes through call_model() or call_model_json()
here instead of importing `ollama` directly, so:
- model name/host is one config-driven place (backend/config.py)
- retry/timeout handling is written once
- JSON-mode parsing failures are a distinct, catchable error type

Callers are responsible for what the prompt asks the model to return —
this module only owns the transport.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import ollama

from backend import config

logger = logging.getLogger(__name__)

# A single shared client, pointed at the host from config. Cheap to construct
# but no reason to rebuild it per call.
_client = ollama.Client(host=config.OLLAMA_HOST)


class OllamaError(RuntimeError):
    """
    Raised for both transport failures (Ollama not running, connection
    refused, timeout after retries) and content failures (model didn't
    return valid JSON when json_mode was requested). Callers generally
    treat both the same way -- surface a 502-ish "AI backend unavailable
    or misbehaved" to the API layer -- so one error type keeps their
    except clauses simple.
    """


def call_model(
    prompt: str,
    system: Optional[str] = None,
    *,
    model: Optional[str] = None,
    json_mode: bool = True,
    temperature: float = 0.2,
    max_retries: int = 2,
    retry_backoff_seconds: float = 1.5,
) -> str:
    """
    Send a single prompt (+ optional system prompt) to the local Ollama
    model and return the raw text of the response.

    Retries only transport-level failures (connection refused, timeout,
    Ollama not yet warmed up) -- not malformed model output, since retrying
    a bad prompt with the same prompt just wastes a local inference pass.
    That distinction lives in call_model_json(), which is where malformed
    JSON actually surfaces.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    chat_kwargs: dict[str, Any] = {
        "model": model or config.OLLAMA_MODEL,
        "messages": messages,
        "options": {"temperature": temperature},
    }
    if json_mode:
        chat_kwargs["format"] = "json"

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            response = _client.chat(**chat_kwargs)
            return response["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - ollama's client raises several exception types
            last_error = exc
            logger.warning(
                "Ollama call failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * (attempt + 1))

    raise OllamaError(
        f"Could not reach Ollama at {config.OLLAMA_HOST} after "
        f"{max_retries + 1} attempt(s): {last_error}"
    ) from last_error


def call_model_json(
    prompt: str,
    system: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """
    Like call_model(), but parses the response as JSON and raises
    OllamaError (not json.JSONDecodeError) on invalid JSON, so every
    caller can catch one exception type regardless of whether Ollama
    was unreachable or just returned garbage.
    """
    raw = call_model(prompt, system=system, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError(
            f"Model did not return valid JSON: {exc}. Raw output (truncated): {raw[:500]!r}"
        ) from exc
