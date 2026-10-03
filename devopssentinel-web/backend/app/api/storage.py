"""Storage endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import validate_name
from ..services.parsers import normalize_pvcs
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["storage"])


def _pvcs(lines: list[str], ns: str) -> list[dict]:
    return [p.model_dump() for p in normalize_pvcs(lines, ns)]


@router.get("/storage")
async def storage(sc: Scope = Depends(scope)) -> dict:
    return await invoke("storage.dependencies", sc, normalizer=_pvcs)


@router.get("/storage/pvc/{name}")
async def pvc_detail(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="pvc")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "PersistentVolumeClaim", "name": name},
    )


@router.get("/storage/consumers/{name}")
async def pvc_consumers(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="pvc")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "PersistentVolumeClaim", "name": name},
    )


@router.get("/storage/mount-warnings")
async def mount_warnings(sc: Scope = Depends(scope)) -> dict:
    result = await invoke("storage.dependencies", sc, normalizer=_pvcs)
    data = result["envelope"]["data"] or []
    warnings = [p for p in data if p.get("severity") != "OK"]
    result["envelope"]["data"] = warnings
    if warnings:
        result["envelope"]["status"] = "WARNING"
    return result
