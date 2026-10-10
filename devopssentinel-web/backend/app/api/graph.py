"""Dependency graph, impact and failure-path endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..security import validate_kind, validate_name
from ..services.parsers import normalize_dependency_graph, normalize_findings
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["graph"])


def dependency_graph(lines: list[str], _ns: str) -> dict:
    """Normalizer shared by every route that reads a dependency report."""
    return normalize_dependency_graph(lines).model_dump()


def reverse_dependencies(graph_data: dict, target: str) -> dict:
    """Objects that reference ``target``, read from the engine's own edges.

    Used by every "what consumes this?" surface (certificate consumers, PVC
    consumers, blast radius). The relationship is always taken from an edge the
    engine emitted, so nothing here is inferred (spec sections 41, 347).
    """
    direct = sorted({edge["source"] for edge in graph_data.get("edges", []) if edge.get("target") == target})
    return {
        "target": target,
        "direct": direct,
        "count": len(direct),
        "graph": graph_data,
        "confidence": "HIGH CONFIDENCE",
    }


def _findings(lines: list[str], ns: str) -> list[dict]:
    """Same normalizer the findings queue uses, so health never disagrees."""
    return [f.model_dump() for f in normalize_findings(lines, ns)]


def _ref(value: str) -> str:
    """Reduce a resource reference to ``Kind/name``.

    Findings sometimes carry a namespace prefix (``flux-system/Pod/web``) where
    the graph uses ``Pod/web``. Taking the last two segments makes the two
    comparable without inventing a match.
    """
    parts = [part for part in str(value).split("/") if part]
    return f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else str(value)


async def reverse_dependency_result(kind: str, name: str, sc: Scope) -> dict:
    """Fetch a dependency report and reshape it as reverse dependencies."""
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=dependency_graph,
    )
    graph_data = result["envelope"]["data"] or {"nodes": [], "edges": []}
    result["envelope"]["data"] = reverse_dependencies(graph_data, f"{kind}/{name}")
    return result


@router.get("/graph/{kind}/{name}")
async def graph(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    validate_kind(kind)
    validate_name(name)
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=dependency_graph,
    )


@router.get("/graph/gitops")
async def gitops_graph(sc: Scope = Depends(scope)) -> dict:
    return await invoke("graph.gitops", sc, normalizer=dependency_graph)


@router.get("/impact/{kind}/{name}")
async def impact(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    """Reverse dependencies (what references this object).

    Derived from the engine's dependency report, so relationships carry an
    explicit confidence and are never presented as proven causality.
    """
    validate_kind(kind)
    validate_name(name)
    return await reverse_dependency_result(kind, name, sc)


@router.get("/failure-path/{kind}/{name}")
async def failure_path(
    kind: str, name: str, sc: Scope = Depends(scope), force: bool = Query(False)
) -> dict:
    """The unhealthy chain through this object.

    The dependency report describes *structure*, not health, so the graph alone
    can never say which node is failing. Node state therefore comes from the
    engine's own findings — the same operation the findings queue reads. A node
    is only highlighted when a finding names it, and the payload records that
    provenance so the UI never implies the graph carried the health itself
    (spec sections 40, 52, 286).
    """
    validate_kind(kind)
    validate_name(name)
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=dependency_graph,
        force=force,
    )
    graph_data = result["envelope"]["data"] or {"nodes": [], "edges": []}

    findings = await invoke("workloads.triage", sc, normalizer=_findings, force=force)
    severity_by_ref: dict[str, str] = {}
    for finding in findings["envelope"]["data"] or []:
        severity = str(finding.get("severity", "UNKNOWN"))
        reference = _ref(finding.get("resource", ""))
        if reference and severity in ("FAILED", "CRITICAL", "WARNING"):
            severity_by_ref.setdefault(reference, severity)

    unhealthy: dict[str, str] = {}
    for node in graph_data.get("nodes", []):
        severity = severity_by_ref.get(_ref(node.get("id", "")))
        if severity:
            # The graph report has no state of its own; this one is the engine's.
            node["state"] = severity
            unhealthy[node["id"]] = severity

    path_edges = [
        edge
        for edge in graph_data.get("edges", [])
        if edge["source"] in unhealthy or edge["target"] in unhealthy
    ]
    result["envelope"]["data"] = {
        "target": f"{kind}/{name}",
        "graph": graph_data,
        "unhealthy": sorted(unhealthy),
        "severity": unhealthy,
        "pathEdges": path_edges,
        "healthSource": "the engine's findings",
        "note": (
            "Health is read from the engine's findings, not from the dependency "
            "report. A node with no finding is left UNKNOWN rather than assumed "
            "healthy."
        ),
    }
    if unhealthy:
        result["envelope"]["status"] = max(
            (unhealthy.values()),
            key=lambda value: {"FAILED": 3, "CRITICAL": 3, "WARNING": 2}.get(value, 0),
        )
    return result


@router.get("/path")
async def path(
    kind: str,
    name: str,
    sc: Scope = Depends(scope),
) -> dict:
    return await graph(kind, name, sc)
