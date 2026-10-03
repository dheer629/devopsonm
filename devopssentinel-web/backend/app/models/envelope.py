"""Standard response envelope shared by every API endpoint (spec section 8)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from ..config import API_SCHEMA_VERSION

T = TypeVar("T")

Source = Literal["LIVE", "CACHE", "LOCAL", "PARTIAL", "UNAVAILABLE"]
Status = Literal[
    "OK",
    "INFO",
    "NOTICE",
    "WARNING",
    "CRITICAL",
    "FAILED",
    "UNKNOWN",
    "PARTIAL",
    "UNAVAILABLE",
]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Envelope(BaseModel, Generic[T]):
    schemaVersion: str = API_SCHEMA_VERSION
    toolVersion: str = "UNKNOWN"
    timestamp: str = Field(default_factory=utcnow_iso)
    context: str = ""
    namespace: str = ""
    source: Source = "LIVE"
    status: Status = "OK"
    partial: bool = False
    durationMs: int = 0
    cacheAgeMs: int = 0
    data: T | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EngineLineEnvelope(BaseModel):
    """Mirrors the engine's own ``--json`` object verbatim (never re-parsed)."""

    schema_version: str = "1.0"
    application: str = "DevOpsSentinel"
    tool_version: str = "UNKNOWN"
    version: str = "UNKNOWN"
    title: str = ""
    context: str = ""
    namespace: str = ""
    timestamp: str = ""
    collected: str = ""
    exit_status: int = 0
    lines: list[str] = Field(default_factory=list)


class OperationInfo(BaseModel):
    """Allowlisted operation descriptor exposed via /capabilities."""

    id: str
    title: str
    domain: str
    mode: str
    args: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    timeoutS: float = 45.0


class RawEvidence(BaseModel):
    """Raw expert view: never hidden behind normalized interpretation."""

    engineArgv: list[str]
    readOnlyCommand: str
    exitStatus: int
    stdout: str
    stderr: str
    durationMs: int


class EnvelopeWithRaw(BaseModel, Generic[T]):
    envelope: Envelope[T]
    raw: RawEvidence | None = None


def make_envelope(
    data: Any,
    *,
    tool_version: str = "UNKNOWN",
    context: str = "",
    namespace: str = "",
    source: Source = "LIVE",
    status: Status = "OK",
    partial: bool = False,
    duration_ms: int = 0,
    cache_age_ms: int = 0,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> Envelope[Any]:
    return Envelope[Any](
        toolVersion=tool_version,
        context=context,
        namespace=namespace,
        source=source,
        status=status,
        partial=partial,
        durationMs=duration_ms,
        cacheAgeMs=cache_age_ms,
        data=data,
        warnings=warnings or [],
        errors=errors or [],
    )
