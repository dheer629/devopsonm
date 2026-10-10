"""Shared pytest fixtures for the DevOpsSentinel Web backend."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_ENGINE = FIXTURES / "fake_engine.py"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def fake_runner():
    """A Runner wired to the fake engine using the current interpreter."""
    from app.services.runner import Runner

    return Runner(engine_path=FAKE_ENGINE, bash_binary=sys.executable)


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """Point every local-state write at a throwaway directory.

    The connection choice, the live-feature flags, pins, notes and the audit
    trail all live under ``settings.state_dir``. A test must never write into
    the operator's real ``~/.devopssentinel-web``.
    """
    from app.config import settings

    target = tmp_path / "state"
    target.mkdir()
    monkeypatch.setattr(settings, "state_dir", target)
    return target


@pytest.fixture()
def client(fake_runner, monkeypatch):
    from app.services import sentinel

    monkeypatch.setattr(sentinel.adapter, "runner", fake_runner)
    # Startup auto-connect must never run during a test: it would spawn docker
    # and kubectl probes against whatever happens to be listening on the host,
    # making the suite slow and machine-dependent.
    from app.config import settings

    monkeypatch.setattr(settings, "autoconnect", False)
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
