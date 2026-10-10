"""Runtime toggles for the two opt-in live-data features.

Both default to OFF and stay off unless an operator turns them on. The Settings
page can switch them without restarting the server, so a container does not have
to be recreated with extra environment variables just to expose the read-only
SQL console or the Kafka topic lister.

Environment variables still win at start-up: ``DSWEB_ENABLE_SQL_CONSOLE`` and
``DSWEB_ENABLE_KAFKA_TOPICS`` are the defaults this store overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import settings


def _file() -> Path:
    path = Path(settings.state_dir) / "live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> dict:
    try:
        payload = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def sql_console_enabled() -> bool:
    stored = _load().get("sqlConsole")
    return settings.enable_sql_console if stored is None else bool(stored)


def kafka_topics_enabled() -> bool:
    stored = _load().get("kafkaTopics")
    return settings.enable_kafka_topics if stored is None else bool(stored)


def set_flags(*, sql_console: bool | None = None, kafka_topics: bool | None = None) -> dict:
    data = _load()
    if sql_console is not None:
        data["sqlConsole"] = bool(sql_console)
    if kafka_topics is not None:
        data["kafkaTopics"] = bool(kafka_topics)
    path = _file()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - defensive
        pass
    return snapshot()


def snapshot() -> dict:
    return {
        "sqlConsole": sql_console_enabled(),
        "kafkaTopics": kafka_topics_enabled(),
    }
