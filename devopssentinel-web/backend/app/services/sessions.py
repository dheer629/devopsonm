"""Local-only operator state: pins, notes, baselines, incident workspace.

Nothing here touches Kubernetes. Everything is written beneath the private
``~/.devopssentinel-web`` directory with ``umask 077``-equivalent handling.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..config import settings


def _state_dir() -> Path:
    path = Path(settings.state_dir)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover - platform dependent
        pass
    return path


def _load(name: str, default: Any) -> Any:
    path = _state_dir() / name
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save(name: str, payload: Any) -> None:
    path = _state_dir() / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Sessions:
    """File-backed operator state. All values are non-secret by construction."""

    def __init__(self) -> None:
        self.started_at = time.time()

    # -- pins ---------------------------------------------------------------
    def pins(self) -> list[dict[str, Any]]:
        return _load("pins.json", [])

    def add_pin(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        pins = self.pins()
        item = {**item, "pinnedAt": int(time.time())}
        pins = [p for p in pins if p.get("id") != item.get("id")]
        pins.insert(0, item)
        _save("pins.json", pins[:200])
        return pins

    def remove_pin(self, pin_id: str) -> list[dict[str, Any]]:
        pins = [p for p in self.pins() if p.get("id") != pin_id]
        _save("pins.json", pins)
        return pins

    # -- history ------------------------------------------------------------
    def history(self) -> list[dict[str, Any]]:
        return _load("history.json", [])

    def push_history(self, item: dict[str, Any]) -> None:
        history = [h for h in self.history() if h.get("id") != item.get("id")]
        history.insert(0, {**item, "visitedAt": int(time.time())})
        _save("history.json", history[:50])

    # -- notes --------------------------------------------------------------
    def notes(self, incident_id: str) -> list[dict[str, Any]]:
        return _load(f"notes-{incident_id}.json", [])

    def add_note(self, incident_id: str, text: str, author: str = "operator") -> list[dict[str, Any]]:
        notes = self.notes(incident_id)
        notes.append({"id": f"n{len(notes) + 1}", "text": text, "author": author, "at": int(time.time())})
        _save(f"notes-{incident_id}.json", notes)
        return notes

    # -- baselines ----------------------------------------------------------
    def baselines(self) -> list[dict[str, Any]]:
        return _load("baselines.json", [])

    def save_baseline(self, name: str, context: str, namespace: str, data: Any) -> dict[str, Any]:
        baselines = self.baselines()
        entry = {
            "name": name,
            "context": context,
            "namespace": namespace,
            "capturedAt": int(time.time()),
            "data": data,
        }
        baselines = [b for b in baselines if b.get("name") != name]
        baselines.insert(0, entry)
        _save("baselines.json", baselines[:50])
        return entry

    def get_baseline(self, name: str) -> dict[str, Any] | None:
        for b in self.baselines():
            if b.get("name") == name:
                return b
        return None

    # -- session info -------------------------------------------------------
    def info(self) -> dict[str, Any]:
        return {
            "startedAt": int(self.started_at),
            "uptimeS": int(time.time() - self.started_at),
            "incidentId": settings.incident_id,
            "stateDir": str(_state_dir()),
        }


sessions = Sessions()
