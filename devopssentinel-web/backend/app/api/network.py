"""Network endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import validate_name
from ..services.parsers import normalize_services
from .deps import Scope, invoke, scope
from .graph import dependency_graph, reverse_dependency_result

router = APIRouter(prefix="/api/v1", tags=["network"])


def _svc(lines: list[str], ns: str) -> list[dict]:
    return [s.model_dump() for s in normalize_services(lines, ns)]


@router.get("/network/services")
async def services(sc: Scope = Depends(scope)) -> dict:
    return await invoke("network.topology", sc, normalizer=_svc)


@router.get("/network/endpoints")
async def endpoints(sc: Scope = Depends(scope)) -> dict:
    """Services with their endpoint counts.

    EndpointSlice detail comes from the same engine report the Services view
    uses; the counts are what the engine observed, not a computed guess.
    """
    result = await invoke("network.topology", sc, normalizer=_svc)
    data = result["envelope"]["data"] or []
    result["envelope"]["data"] = [
        {
            "name": s.get("name", ""),
            "namespace": s.get("namespace", ""),
            "type": s.get("type", ""),
            "cluster_ip": s.get("cluster_ip", ""),
            "ready_endpoints": s.get("ready_endpoints", 0),
            "not_ready_endpoints": s.get("not_ready_endpoints", 0),
            "ports": s.get("ports", ""),
            "status": s.get("status", "UNKNOWN"),
        }
        for s in data
    ]
    return result


@router.get("/network/endpoint-gaps")
async def endpoint_gaps(sc: Scope = Depends(scope)) -> dict:
    result = await invoke("network.topology", sc, normalizer=_svc)
    data = result["envelope"]["data"] or []
    gaps = [
        s for s in data
        if s.get("ready_endpoints", 0) == 0 and s.get("type", "ClusterIP") != "ExternalName"
    ]
    result["envelope"]["data"] = gaps
    if gaps:
        result["envelope"]["status"] = "WARNING"
    return result


@router.get("/network/port-path/{service}")
async def port_path(service: str, sc: Scope = Depends(scope)) -> dict:
    """Ingress → Service → EndpointSlice → Pod, as a typed graph.

    Also returns the Service's own port declaration so the UI can show the
    mapping next to the chain rather than making the operator correlate by eye.
    """
    validate_name(service, field="service")
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Service", "name": service},
        normalizer=dependency_graph,
    )
    services = await invoke("network.topology", sc, normalizer=_svc)
    match = next(
        (s for s in (services["envelope"]["data"] or []) if s.get("name") == service),
        None,
    )
    result["envelope"]["data"] = {
        "service": match,
        "graph": result["envelope"]["data"] or {"nodes": [], "edges": []},
    }
    return result


@router.get("/network/policies/{pod}")
async def policies(pod: str, sc: Scope = Depends(scope)) -> dict:
    """NetworkPolicies that select this pod, plus the pod's own edges.

    ``isolated`` is only true when the engine reported a selecting policy, so an
    empty result means "none observed", never "no policy exists".
    """
    validate_name(pod, field="pod")
    result = await reverse_dependency_result("Pod", pod, sc)
    data = result["envelope"]["data"] or {}
    selecting = [
        edge["source"]
        for edge in (data.get("graph") or {}).get("edges", [])
        if edge.get("target") == f"Pod/{pod}" and "networkpolicy" in edge.get("source", "").lower()
    ]
    data["selectingPolicies"] = sorted(set(selecting))
    data["isolated"] = bool(selecting)
    data["note"] = (
        "Configuration only: DevOpsSentinel reports which policies select the pod, "
        "not whether traffic is actually permitted at runtime."
    )
    return result


@router.get("/network/dns/{service}")
async def dns(service: str, sc: Scope = Depends(scope)) -> dict:
    """Service DNS name, the address the Service declares, and observed endpoints.

    The engine does not query CoreDNS. ``resolves`` is therefore only asserted
    when an endpoint address exists to back it; otherwise the UI says NOT PROBED.
    """
    validate_name(service, field="service")
    services = await invoke("network.topology", sc, normalizer=_svc)
    match = next(
        (s for s in (services["envelope"]["data"] or []) if s.get("name") == service),
        None,
    )
    namespace = match.get("namespace", "") if match else ""
    fqdn = f"{service}.{namespace}.svc.cluster.local" if namespace else service
    ready = int(match.get("ready_endpoints", 0)) if match else 0
    result = await invoke("network.topology", sc, normalizer=_svc)
    result["envelope"]["data"] = {
        "service": match,
        "fqdn": fqdn,
        "shortName": f"{service}.{namespace}" if namespace else service,
        "expectedAddress": match.get("cluster_ip", "") if match else "",
        "readyEndpoints": ready,
        "resolves": "VERIFIED" if ready > 0 else "NOT PROBED",
        "note": (
            "DNS resolution is not probed from the browser adapter; "
            "this reports the Service record and its observed endpoints."
        ),
    }
    return result
