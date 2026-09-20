"""
tests/conftest.py — isolated test environment for the BrainDUMP backend.

The whole app is pointed at a throwaway data directory *before* any
`backend` module is imported (config.py reads BRAINDUMP_DATA_DIR at import
time), so no test can ever touch the real data/tasks.db. Each test then
starts from an empty schema, and Ollama is stubbed out at the transport
layer so a test can never silently depend on a local model being up.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="braindump-tests-"))
os.environ["BRAINDUMP_DATA_DIR"] = str(_TEST_DATA_DIR)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import config  # noqa: E402
from backend.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture()
def tmp_path():
    """Per-test scratch directory that does NOT go through pytest's shared
    `pytest-of-<user>` temp root. That root is created once per machine and
    breaks every test at setup (PermissionError / WinError 5) if it was ever
    created by an elevated shell or has bad permissions -- unrelated to this
    app. Overriding the built-in fixture keeps the suite self-contained."""
    path = Path(tempfile.mkdtemp(prefix="braindump-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)  # SQLite files can be briefly locked on Windows


@pytest.fixture(autouse=True)
def _fresh_db():
    """Empty schema for every test."""
    from backend import models  # noqa: F401  (registers every table on Base.metadata)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _isolated_ml_artifacts(tmp_path, monkeypatch):
    """Keep the trained-estimator pickle (and its in-process cache) out of the real models/ dir."""
    from backend.ml import estimator, trainer

    models_dir = tmp_path / "models"
    monkeypatch.setattr(config, "MODELS_DIR", models_dir)
    monkeypatch.setattr(trainer, "ESTIMATOR_MODEL_PATH", models_dir / "estimator.pkl")
    monkeypatch.setattr(estimator, "_trained_cache", None)
    monkeypatch.setattr(estimator, "_trained_cache_mtime", None)


@pytest.fixture(autouse=True)
def _no_live_ollama(monkeypatch):
    """Any un-mocked LLM call fails loudly as OllamaError instead of hanging on a local server.

    Services do `from ...ollama_client import call_model[_json]`, so patching the
    ollama_client module alone wouldn't reach them -- every importing module's own
    reference is patched too. Tests that need a model response override these
    with `monkeypatch.setattr(<module>, "call_model_json", fake)`.
    """
    from backend.ai import ollama_client
    from backend.scheduler import morning
    from backend.services import ai_coach_service, analytics_service, planner_service, task_parser

    def _refuse(*args, **kwargs):
        raise ollama_client.OllamaError("Ollama is disabled in tests")

    for module, names in (
        (ollama_client, ("call_model", "call_model_json")),
        (task_parser, ("call_model_json",)),
        (planner_service, ("call_model_json",)),
        (analytics_service, ("call_model",)),
        (ai_coach_service, ("call_model",)),
        (morning, ("call_model",)),
    ):
        for name in names:
            monkeypatch.setattr(module, name, _refuse)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    # Session-scoped: the lifespan starts/stops the APScheduler, which is
    # wasteful to do per test. The schema is reset per test by _fresh_db.
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client
