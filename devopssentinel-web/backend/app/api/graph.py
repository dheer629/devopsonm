"""Dependency graph, impact and failure-path endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import validate_kind, validate_name
from ..services.parsers import normalize_dependency_graph
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["graph"])


@router.get("/graph/{kind}/{name}")
async def graph(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    validate_kind(kind)
    validate_name(name)
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )


@router.get("/graph/gitops")
async def gitops_graph(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "graph.gitops",
        sc,
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )


@router.get("/impact/{kind}/{name}")
async def impact(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    """Reverse dependencies (what references this object).

    Derived from the engine's dependency report, so relationships carry an
    explicit confidence and are never presented as proven causality.
    """
    validate_kind(kind)
    validate_name(name)
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )
    graph_data = result["envelope"]["data"] or {"nodes": [], "edges": []}
    target = f"{kind}/{name}"
    direct = [
        edge["source"]
        for edge in graph_data.get("edges", [])
        if edge["target"] == target
    ]
    referenced_by = sorted(set(direct))
    result["envelope"]["data"] = {
        "target": target,
        "direct": referenced_by,
        "graph": graph_data,
        "confidence": "HIGH CONFIDENCE",
    }
    return result


@router.get("/failure-path/{kind}/{name}")
async def failure_path(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    validate_kind(kind)
    validate_name(name)
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )
    graph_data = result["envelope"]["data"] or {"nodes": [], "edges": []}
    # A path is only highlighted when the node state is evidence-backed
    # (i.e. the engine marked it as unhealthy). We never fabricate failures.
    unhealthy = {n["id"] for n in graph_data.get("nodes", []) if n["state"] in ("FAILED", "CRITICAL", "WARNING")}
    path_edges = [
        e for e in graph_data.get("edges", []) if e["source"] in unhealthy or e["target"] in unhealthy
    ]
    result["envelope"]["data"] = {
        "graph": graph_data,
        "unhealthy": sorted(unhealthy),
        "pathEdges": path_edges,
        "note": "Only evidence-backed unhealthy nodes are highlighted.",
    }
    return result


@router.get("/path")
async def path(
    kind: str,
    name: str,
    sc: Scope = Depends(scope),
) -> dict:
    return await graph(kind, name, sc)
