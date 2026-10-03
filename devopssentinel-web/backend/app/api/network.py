"""Network endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import validate_name
from ..services.parsers import normalize_services
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["network"])


def _svc(lines: list[str], ns: str) -> list[dict]:
    return [s.model_dump() for s in normalize_services(lines, ns)]


@router.get("/network/services")
async def services(sc: Scope = Depends(scope)) -> dict:
    return await invoke("network.topology", sc, normalizer=_svc)


@router.get("/network/endpoints")
async def endpoints(sc: Scope = Depends(scope)) -> dict:
    return await invoke("network.topology", sc, normalizer=_svc)


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
    validate_name(service, field="service")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Service", "name": service},
    )


@router.get("/network/policies/{pod}")
async def policies(pod: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(pod, field="pod")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Pod", "name": pod},
    )


@router.get("/network/dns/{service}")
async def dns(service: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(service, field="service")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Service", "name": service},
    )
