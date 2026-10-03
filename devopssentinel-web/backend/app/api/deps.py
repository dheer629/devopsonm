"""Shared API helpers: scope extraction and envelope construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Query

from ..config import settings
from ..models import Envelope, make_envelope
from ..security import validate_context, validate_name
from ..services.cache import cache
from ..services.runner import RunResult
from ..services.sentinel import adapter

# Engine exit-code -> envelope status (documented in the engine README).
EXIT_STATUS = {
    0: "OK",
    1: "WARNING",
    2: "FAILED",
    3: "FAILED",
    4: "PARTIAL",
    124: "FAILED",
    127: "UNAVAILABLE",
}


@dataclass
class Scope:
    context: str = ""
    namespace: str = ""


def scope(
    context: str = Query("", description="kubeconfig context (validated)"),
    namespace: str = Query("", description="namespace (validated)"),
) -> Scope:
    try:
        ctx = validate_context(context) if context else ""
        ns = validate_name(namespace, field="namespace") if namespace else ""
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Scope(context=ctx, namespace=ns)


def _raw(result: RunResult) -> dict[str, Any]:
    return {
        "engineArgv": result.argv,
        "readOnlyCommand": result.read_only_command,
        "exitStatus": result.exit_status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "durationMs": result.duration_ms,
    }


async def invoke(
    operation_id: str,
    sc: Scope,
    *,
    params: dict | None = None,
    normalizer: Callable[[list[str], str], Any] | None = None,
    force: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Run an allowlisted operation and return an envelope dict.

    ``normalizer(lines, namespace)`` converts the engine's plain report lines
    into typed rows. If omitted, ``data`` holds the raw lines plus metadata.
    """
    params = params or {}
    key = f"{operation_id}|{sc.context}|{sc.namespace}|{sorted(params.items())}"

    async def factory() -> dict[str, Any]:
        result, engine = await adapter.invoke(
            operation_id, context=sc.context, namespace=sc.namespace, params=params
        )
        if engine is None:
            return {
                "engine": None,
                "lines": [],
                "raw": _raw(result),
                "exit": result.exit_status,
                "error": result.error,
                "timedOut": result.timed_out,
                "truncated": result.truncated,
            }
        return {
            "engine": engine.model_dump(),
            "lines": engine.lines,
            "raw": _raw(result),
            "exit": result.exit_status,
            "error": result.error,
            "timedOut": result.timed_out,
            "truncated": result.truncated,
        }

    if force:
        cache.invalidate(key)
    payload, age_ms, from_cache = await cache.get_or_set(key, factory)

    engine = payload.get("engine") or {}
    lines = payload.get("lines") or []
    exit_status = payload.get("exit", 0)
    status = EXIT_STATUS.get(exit_status, "UNKNOWN")
    partial = status == "PARTIAL" or bool(payload.get("truncated"))
    warnings: list[str] = []
    errors: list[str] = []

    if payload.get("timedOut"):
        errors.append(payload.get("error") or "operation timed out")
    elif payload.get("error"):
        errors.append(payload["error"])
    if payload.get("truncated"):
        warnings.append("output truncated at the configured size limit")
    if engine.get("lines") is None:
        errors.append("engine produced no machine-readable output")

    data: Any
    if normalizer is not None and lines:
        data = normalizer(lines, sc.namespace)
    elif normalizer is not None:
        data = []
    else:
        data = {"title": engine.get("title", ""), "lines": lines}

    envelope = make_envelope(
        data,
        tool_version=engine.get("tool_version", "UNKNOWN"),
        context=sc.context or engine.get("context", ""),
        namespace=sc.namespace or engine.get("namespace", ""),
        source="CACHE" if from_cache else ("PARTIAL" if partial else "LIVE"),
        status=status,
        partial=partial,
        duration_ms=payload["raw"]["durationMs"],
        cache_age_ms=age_ms,
        warnings=warnings,
        errors=errors,
    )
    return {
        "envelope": envelope.model_dump(),
        "raw": payload["raw"] if settings.debug or True else None,
        "exitStatus": exit_status,
    }
