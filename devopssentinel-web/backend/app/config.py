"""Runtime configuration for DevOpsSentinel Web.

The Bash engine (DevOps_K8s_Sentinel_FINAL_GP.sh) remains the operational
source of truth. This backend is a thin, read-only adapter around it.
"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEB_VERSION = "1.0.0"
API_SCHEMA_VERSION = "1.0"
SUPERVISION_MODE = "SUPERVISION [READ ONLY]"

# Repo root is .../devopssentinel-web ; the engine lives one level up.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _PROJECT_ROOT.parent

DEFAULT_ENGINE = _REPO_ROOT / "DevOps_K8s_Sentinel_FINAL_GP.sh"


class Settings(BaseSettings):
    """Environment-driven settings. All values are safe-by-default."""

    model_config = SettingsConfigDict(env_prefix="DSWEB_", env_file=None, extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765

    # Path to the canonical Bash engine.
    engine_path: Path = Field(default_factory=lambda: DEFAULT_ENGINE)
    # Interpreter used to run the engine (bash on Linux/WSL).
    bash_binary: str = "bash"

    # Local, private state root (pins, notes, baselines, incidents, audit).
    state_dir: Path = Field(
        default_factory=lambda: Path(os.environ.get("HOME", str(Path.home())))
        / ".devopssentinel-web"
    )

    # Frontend build output served by FastAPI.
    frontend_dist: Path = Field(default_factory=lambda: _PROJECT_ROOT / "frontend" / "dist")

    # Allowlisted browser origins (never a wildcard).
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    @model_validator(mode="after")
    def _trust_the_origin_we_are_served_on(self) -> "Settings":
        """Always allow the origin this process is actually reachable on.

        ``DSWEB_PORT`` / ``--port`` (and ``DSWEB_HOST``) used to change where the
        app listens *without* changing the allow-list, so the page and the API
        disagreed about who was trusted: every GET worked, and every POST was
        answered ``403 origin not allowed``. The console then read as connected
        while nothing could be saved, refreshed or connected. A same-origin
        request is not cross-site, so the serving origin is always trusted;
        ``DSWEB_ALLOWED_ORIGINS`` still narrows every other origin, and the list
        is never a wildcard.
        """
        for origin in self.self_origins():
            if origin not in self.allowed_origins:
                self.allowed_origins.append(origin)
        return self

    def self_origins(self) -> list[str]:
        """The origins this process can be reached on, from the configured bind.

        A wildcard bind answers on loopback like any other bind, so the
        documented access path keeps working. A LAN address is deliberately *not*
        trusted implicitly -- add it to ``DSWEB_ALLOWED_ORIGINS``.
        """
        host = (self.host or "").strip().lower()
        if host in {"127.0.0.1", "localhost", "", "*", "0.0.0.0", "::", "[::]"}:
            names = ["127.0.0.1", "localhost"]
        else:
            names = [host]
        return [f"http://{name}:{self.port}" for name in names]

    # Operation bounds.
    default_timeout_s: float = 45.0
    max_timeout_s: float = 300.0
    max_output_bytes: int = 8 * 1024 * 1024
    max_concurrency: int = 4

    # Cache.
    cache_ttl_s: float = 15.0

    debug: bool = False
    incident_id: str | None = None
    open_browser: bool = False

    # Auto-connect on startup. A console that opens with no working cluster
    # connection looks broken, so the backend looks for one itself -- endpoint
    # discovery plus credential pairing -- instead of waiting for the operator
    # to press a button. It never overrides a connection that already works.
    #   DSWEB_AUTOCONNECT=0 -> never connect automatically
    autoconnect: bool = True

    # Opt-in live-data features. Both default to OFF so the browser stays a pure
    # read-only supervision surface unless the operator explicitly enables them.
    #   DSWEB_ENABLE_SQL_CONSOLE=1     -> POST /api/v1/database/query
    #   DSWEB_ENABLE_KAFKA_TOPICS=1    -> POST /api/v1/kafka/topics
    # See docs/SECURITY.md for the full contract.
    enable_sql_console: bool = False
    enable_kafka_topics: bool = False
    sql_max_rows: int = 200
    sql_timeout_s: float = 15.0
    kafka_timeout_s: float = 8.0

    def engine_available(self) -> bool:
        return self.engine_path.is_file()

    def bash_available(self) -> bool:
        return shutil.which(self.bash_binary) is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
