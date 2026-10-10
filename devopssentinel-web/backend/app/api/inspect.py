"""Log viewer + resource description viewer.

The engine captures pod logs and describes resources only in its interactive
console (there is no ``--logs`` / ``--describe`` report mode), so these two
read-only views are backed by narrowly-scoped ``kubectl`` calls in
``services.kube``. Every form is pinned there; Secret payloads are never
requested and every stream is redacted before it leaves the process.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import make_envelope
from ..security import redact_text, validate_kind, validate_name
from ..services import kube
from ..services.parsers import normalize_kube_logs
from .deps import Scope, scope

router = APIRouter(prefix="/api/v1", tags=["inspect"])

# The bounded time-window options the viewer offers. `""` means "no time limit".
SINCE_OPTIONS = ("5m", "15m", "30m", "1h", "6h", "24h")
DESCRIBE_FORMATS = ("describe", "yaml", "json", "events")


def _raw(argv: list[str], stdout: str, *, duration_ms: int, stderr: str = "") -> dict:
    """A ``RawEvidence``-shaped expert view for a kubectl-backed read."""
    return {
        "engineArgv": ["kubectl", *argv],
        "readOnlyCommand": kube.command_string(argv),
        "exitStatus": 0,
        "stdout": stdout,
        "stderr": stderr,
        "durationMs": duration_ms,
    }


def _require_namespace(sc: Scope) -> str:
    if not sc.namespace:
        raise HTTPException(
            status_code=400,
            detail="a namespace is required -- select one in the top bar",
        )
    return sc.namespace


@router.get("/logs")
async def logs(
    pod: str = Query(..., description="pod name (validated)"),
    container: str = Query("", description="container name (optional)"),
    tail: int = Query(500, ge=1, le=100000),
    since: str = Query("", description="e.g. 5m, 1h, 24h (empty = no time limit)"),
    previous: bool = Query(False, description="read the previous container instance"),
    timestamps: bool = Query(True, description="prefix each line with its RFC3339 time"),
    sc: Scope = Depends(scope),
) -> dict:
    """One read-only ``kubectl logs`` with the viewer's option surface."""
    validate_name(pod, field="pod")
    if container:
        validate_name(container, field="container")
    if since and since not in SINCE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"unsupported since: {since!r}")
    _require_namespace(sc)

    containers: list[str] = []
    try:
        containers = await kube.pod_containers(pod, context=sc.context, namespace=sc.namespace)
    except kube.KubeError:
        containers = []
    if container and containers and container not in containers:
        raise HTTPException(
            status_code=400, detail=f"pod {pod} has no container {container!r}"
        )

    argv = kube.logs_argv(
        pod,
        context=sc.context,
        namespace=sc.namespace,
        container=container,
        tail=tail,
        since=since,
        previous=previous,
        timestamps=timestamps,
    )
    started = time.perf_counter()
    try:
        text = await kube.pod_logs(
            pod,
            context=sc.context,
            namespace=sc.namespace,
            container=container,
            tail=tail,
            since=since,
            previous=previous,
            timestamps=timestamps,
        )
    except kube.KubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    text = redact_text(text)

    bundle = normalize_kube_logs(
        text.splitlines(),
        pod=pod,
        container=container,
        previous=previous,
        since=since,
        tail=tail,
        timestamps=timestamps,
        containers=containers,
    )
    envelope = make_envelope(
        bundle.model_dump(),
        context=sc.context,
        namespace=sc.namespace,
        source="LIVE",
        status="OK" if bundle.lines else "UNKNOWN",
        duration_ms=duration_ms,
    )
    return {
        "envelope": envelope.model_dump(),
        "raw": _raw(argv, text, duration_ms=duration_ms),
        "exitStatus": 0,
    }


@router.get("/containers")
async def containers(pod: str = Query(...), sc: Scope = Depends(scope)) -> dict:
    """Container names for one pod, so the log viewer can populate its picker."""
    validate_name(pod, field="pod")
    _require_namespace(sc)
    try:
        names = await kube.pod_containers(pod, context=sc.context, namespace=sc.namespace)
    except kube.KubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return make_envelope(
        {"pod": pod, "containers": names},
        context=sc.context,
        namespace=sc.namespace,
        source="LIVE",
        status="OK" if names else "UNKNOWN",
    ).model_dump()


@router.get("/describe")
async def describe(
    kind: str = Query(..., description="resource kind, e.g. Deployment"),
    name: str = Query(..., description="resource name (validated)"),
    format: str = Query("describe", description="describe | yaml | json | events"),
    sc: Scope = Depends(scope),
) -> dict:
    """Read-only describe / get -o yaml|json / events for one resource.

    ``Secret`` is rejected by the kubectl allowlist, so a Secret payload can
    never be requested through this endpoint.
    """
    validate_kind(kind)
    validate_name(name, field="name")
    # Defence in depth: the kubectl allowlist also refuses Secret, but the API
    # states the contract explicitly so a caller gets a clear 403.
    if kind.lower() in ("secret", "secrets"):
        raise HTTPException(
            status_code=403,
            detail="Secret payloads are never read; describe a non-Secret kind",
        )
    fmt = (format or "describe").lower()
    if fmt not in DESCRIBE_FORMATS:
        raise HTTPException(status_code=400, detail=f"unsupported format: {format!r}")
    _require_namespace(sc)

    if fmt == "events":
        argv = kube.events_argv(context=sc.context, namespace=sc.namespace)
        started = time.perf_counter()
        try:
            rows = await kube.namespace_events(
                context=sc.context, namespace=sc.namespace, name=name
            )
        except kube.KubeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = {
            "kind": kind,
            "name": name,
            "namespace": sc.namespace,
            "format": fmt,
            "content": "",
            "events": rows,
        }
        envelope = make_envelope(
            payload,
            context=sc.context,
            namespace=sc.namespace,
            source="LIVE",
            status="OK" if rows else "UNKNOWN",
            duration_ms=duration_ms,
        )
        return {
            "envelope": envelope.model_dump(),
            "raw": _raw(argv, str(rows), duration_ms=duration_ms),
            "exitStatus": 0,
        }

    argv = kube.describe_argv(
        kind, name, context=sc.context, namespace=sc.namespace, fmt=fmt
    )
    started = time.perf_counter()
    try:
        text = await kube.describe_resource(
            kind, name, context=sc.context, namespace=sc.namespace, fmt=fmt
        )
    except kube.KubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    text = redact_text(text)

    payload = {
        "kind": kind,
        "name": name,
        "namespace": sc.namespace,
        "format": fmt,
        "content": text,
        "events": [],
    }
    envelope = make_envelope(
        payload,
        context=sc.context,
        namespace=sc.namespace,
        source="LIVE",
        status="OK" if text.strip() else "UNKNOWN",
        duration_ms=duration_ms,
    )
    return {
        "envelope": envelope.model_dump(),
        "raw": _raw(argv, text, duration_ms=duration_ms),
        "exitStatus": 0,
    }
