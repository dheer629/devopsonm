"""GitOps endpoints (Flux sources, Kustomizations, HelmReleases)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..security import validate_kind, validate_name
from ..services.parsers import normalize_gitops
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["gitops"])


@router.get("/gitops")
async def gitops(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )


@router.get("/gitops/sources")
async def sources(sc: Scope = Depends(scope)) -> dict:
    result = await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )
    data = result["envelope"]["data"] or []
    result["envelope"]["data"] = [
        g for g in data if g.get("kind", "").lower() in
        ("gitrepository", "ocirepository", "helmrepository", "bucket", "source")
    ]
    return result


@router.get("/gitops/kustomizations")
async def kustomizations(sc: Scope = Depends(scope)) -> dict:
    result = await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )
    data = result["envelope"]["data"] or []
    result["envelope"]["data"] = [
        g for g in data if g.get("kind", "").lower() in ("kustomization", "kustomizations")
    ]
    return result


@router.get("/gitops/helmreleases")
async def helmreleases(sc: Scope = Depends(scope)) -> dict:
    result = await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )
    data = result["envelope"]["data"] or []
    result["envelope"]["data"] = [
        g for g in data if g.get("kind", "").lower() in ("helmrelease", "helmreleases")
    ]
    return result


@router.get("/gitops/{kind}/{name}")
async def gitops_detail(
    kind: str,
    name: str,
    sc: Scope = Depends(scope),
    force: bool = Query(False),
) -> dict:
    validate_kind(kind)
    validate_name(name)
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        force=force,
    )


@router.get("/gitops/{kind}/{name}/timeline")
async def gitops_timeline(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    validate_kind(kind)
    validate_name(name)
    return await invoke("graph.dependency", sc, params={"kind": kind, "name": name})


@router.get("/gitops/chain")
async def gitops_chain(sc: Scope = Depends(scope)) -> dict:
    from ..services.parsers import normalize_dependency_graph

    return await invoke(
        "graph.gitops",
        sc,
        normalizer=lambda lines, ns: normalize_dependency_graph(lines).model_dump(),
    )
