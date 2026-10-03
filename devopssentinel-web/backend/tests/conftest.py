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
def client(fake_runner, monkeypatch):
    from app.services import sentinel

    monkeypatch.setattr(sentinel.adapter, "runner", fake_runner)
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
