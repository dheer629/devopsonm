"""Runtime configuration for DevOpsSentinel Web.

The Bash engine (DevOps_K8s_Sentinel_FINAL_GP.sh) remains the operational
source of truth. This backend is a thin, read-only adapter around it.
"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import Field
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

    def engine_available(self) -> bool:
        return self.engine_path.is_file()

    def bash_available(self) -> bool:
        return shutil.which(self.bash_binary) is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
