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
from backend.database import Base, engine  # noqa: E402


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
def user():
    """The signed-in user for this test: `db` is scoped to them and `client`
    sends their bearer token, so a test that uses both sees one consistent
    tenant. Tests that need a second tenant use `make_user()` directly."""
    from tests.helpers import make_user

    return make_user("user@example.com", "Primary User")


@pytest.fixture()
def db(user):
    """A tenant-scoped Session for `user` (db.info["user_id"] set), i.e. exactly
    what a request or background-job iteration for that user gets -- so
    services and factories that call owner_id(db) work as they do in prod."""
    from tests.helpers import scoped_session

    session = scoped_session(user)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def _app_client():
    # Session-scoped: the lifespan starts/stops the APScheduler, which is
    # wasteful to do per test. The schema is reset per test by _fresh_db.
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def client(_app_client, user):
    """The shared TestClient, authenticated as `user` for the duration of the
    test. Per-request `headers=` (e.g. another user's, or none via
    client.get(url, headers={"Authorization": ""}) ) still take precedence."""
    from tests.helpers import auth_headers

    _app_client.headers.update(auth_headers(user))
    try:
        yield _app_client
    finally:
        _app_client.headers.pop("Authorization", None)


@pytest.fixture()
def anon_client(_app_client):
    """The shared TestClient with no credentials at all."""
    _app_client.headers.pop("Authorization", None)
    return _app_client


@pytest.fixture(autouse=True)
def _reset_auth_rate_limits():
    """The limiters are in-process globals keyed on client IP, and every TestClient
    request comes from the same "testclient" host -- without this, failed logins would
    pile up across tests and start returning 429 for unrelated ones."""
    from backend.api.auth import reset_rate_limits

    reset_rate_limits()
    yield


@pytest.fixture(scope="session", autouse=True)
def _cheap_password_hashing():
    """bcrypt's default cost (12 rounds, ~0.25s/hash) is the point in production but makes
    the auth tests -- which hash on every register and every unknown-email login -- crawl.
    Hashes made at any cost still verify, so this only speeds up *new* hashes."""
    from backend.auth import security

    security._pwd_context.update(bcrypt__rounds=4)
    yield
