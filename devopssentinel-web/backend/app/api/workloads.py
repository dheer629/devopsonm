"""Workload / pod endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..models import make_envelope
from ..security import validate_kind, validate_name
from ..services.parsers import (
    normalize_dependency_graph,
    normalize_events,
    normalize_logs,
    normalize_pods,
    normalize_workloads,
)
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["workloads"])


async def _resolve_pod_owner(sc: Scope, name: str) -> str:
    """Resolve a Pod to its owning workload.

    The engine's ``--triage-workload`` correlates *workload* objects
    (Deployment/StatefulSet/DaemonSet/ReplicaSet); passing ``Pod/x`` makes it
    answer ``WORKLOAD NOT FOUND`` and exit 2. We therefore triage the owner and
    let the engine correlate the pod through its own report.
    """
    result = await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)],
    )
    for pod in result["envelope"]["data"] or []:
        if pod.get("name") == name and pod.get("owner"):
            return str(pod["owner"])
    return ""


async def _pod_scope_params(sc: Scope, name: str) -> dict:
    """Build triage params for a pod, preferring its owning workload."""
    owner = await _resolve_pod_owner(sc, name)
    if owner and "/" in owner:
        kind, _, workload = owner.partition("/")
        return {"kind": kind, "name": workload}
    return {"kind": "Pod", "name": name}


@router.get("/workloads")
async def workloads(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [
            w.model_dump() for w in normalize_workloads(lines, ns)
        ],
    )


@router.get("/pods")
async def pods(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)],
    )


@router.get("/pods/{name}")
async def pod_detail(
    name: str, sc: Scope = Depends(scope), force: bool = Query(False)
) -> dict:
    validate_name(name, field="pod")
    return await invoke(
        "workloads.triage_workload",
        sc,
        params=await _pod_scope_params(sc, name),
        force=force,
    )


@router.get("/pods/{name}/containers")
async def pod_containers(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="pod")
    result = await invoke("workloads.triage_workload", sc, params=await _pod_scope_params(sc, name))
    lines: list[str] = result["raw"].get("stdout", "").splitlines()
    containers = [
        line.strip().lstrip("-* ")
        for line in lines
        if "container" in line.lower() and ":" in line
    ][:32]
    envelope = make_envelope(
        {"pod": name, "containers": containers},
        context=sc.context,
        namespace=sc.namespace,
        source=result["envelope"]["source"],
        status="OK" if containers else "UNKNOWN",
    )
    return {"envelope": envelope.model_dump(), "raw": result["raw"]}


@router.get("/pods/{name}/events")
async def pod_events(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="pod")

    def normalizer(lines: list[str], ns: str) -> list[dict]:
        return [e.model_dump() for e in normalize_events(lines, ns)]

    return await invoke(
        "workloads.triage_workload",
        sc,
        params=await _pod_scope_params(sc, name),
        normalizer=normalizer,
    )


@router.get("/pods/{name}/logs")
async def pod_logs(
    name: str,
    sc: Scope = Depends(scope),
    container: str = Query(""),
    previous: bool = Query(False),
    tail: int = Query(500, ge=1, le=100000),
) -> dict:
    """Logs are CLI-only in the engine's interactive menu.

    We surface whatever the triage report captured, normalized, and mark the
    result PARTIAL so the UI never implies a complete log stream.
    """
    validate_name(name, field="pod")
    result = await invoke("workloads.triage_workload", sc, params=await _pod_scope_params(sc, name))
    lines: list[str] = result["raw"].get("stdout", "").splitlines()
    bundle = normalize_logs(lines[-tail:], pod=name, container=container, previous=previous)
    envelope = make_envelope(
        bundle.model_dump(),
        context=sc.context,
        namespace=sc.namespace,
        source="PARTIAL",
        status="PARTIAL",
        partial=True,
        warnings=[
            "Interactive log streaming is CLI-only in the engine; "
            "this view shows report-captured lines."
        ],
    )
    return {"envelope": envelope.model_dump(), "raw": result["raw"]}


@router.get("/pods/{name}/dependencies")
async def pod_dependencies(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="pod")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Pod", "name": name},
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )


@router.get("/workloads/{kind}/{name}")
async def workload_detail(
    kind: str, name: str, sc: Scope = Depends(scope), force: bool = Query(False)
) -> dict:
    validate_kind(kind)
    validate_name(name)
    return await invoke(
        "workloads.triage_workload",
        sc,
        params={"kind": kind, "name": name},
        force=force,
    )
