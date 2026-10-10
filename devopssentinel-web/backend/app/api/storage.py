"""Storage endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import validate_name
from ..services.parsers import normalize_pvcs
from .deps import Scope, invoke, scope
from .graph import reverse_dependency_result

router = APIRouter(prefix="/api/v1", tags=["storage"])


def _pvcs(lines: list[str], ns: str) -> list[dict]:
    return [p.model_dump() for p in normalize_pvcs(lines, ns)]


@router.get("/storage")
async def storage(sc: Scope = Depends(scope)) -> dict:
    return await invoke("storage.dependencies", sc, normalizer=_pvcs)


@router.get("/storage/pvc/{name}")
async def pvc_detail(name: str, sc: Scope = Depends(scope)) -> dict:
    """One claim plus its binding chain (Pod → PVC → PV → StorageClass).

    The claim row comes from the engine's own storage table so the detail view
    can show capacity, access modes and class alongside the relationships.
    """
    validate_name(name, field="pvc")
    claims = await invoke("storage.dependencies", sc, normalizer=_pvcs)
    match = next((p for p in (claims["envelope"]["data"] or []) if p.get("name") == name), None)
    result = await reverse_dependency_result("PersistentVolumeClaim", name, sc)
    result["envelope"]["data"] = {
        "claim": match,
        "graph": (result["envelope"]["data"] or {}).get("graph") or {"nodes": [], "edges": []},
    }
    return result


@router.get("/storage/consumers/{name}")
async def pvc_consumers(name: str, sc: Scope = Depends(scope)) -> dict:
    """Pods and workloads that mount this claim."""
    validate_name(name, field="pvc")
    return await reverse_dependency_result("PersistentVolumeClaim", name, sc)


@router.get("/storage/mount-warnings")
async def mount_warnings(sc: Scope = Depends(scope)) -> dict:
    """Claims the engine did not mark OK, plus claims with no observed consumer.

    An unbound or un-consumed claim is a real operational signal, and the two
    are reported separately so the UI can say which is which.
    """
    result = await invoke("storage.dependencies", sc, normalizer=_pvcs)
    data = result["envelope"]["data"] or []
    warnings = [p for p in data if p.get("severity") != "OK"]
    orphans = [p for p in data if p.get("severity") == "OK" and not p.get("consumers")]
    result["envelope"]["data"] = {
        "warnings": warnings,
        "unconsumed": orphans,
        "total": len(data),
    }
    if warnings:
        result["envelope"]["status"] = "WARNING"
    elif orphans:
        result["envelope"]["status"] = "NOTICE"
    return result
