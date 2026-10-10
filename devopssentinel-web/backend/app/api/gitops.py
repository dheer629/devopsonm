"""GitOps endpoints (Flux sources, Kustomizations, HelmReleases)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..models import make_envelope
from ..security import validate_kind, validate_name
from ..services.parsers import normalize_gitops
from .deps import Scope, invoke, scope
from .graph import dependency_graph

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
    """One GitOps object plus the chain it manages, as a typed graph."""
    validate_kind(kind)
    validate_name(name)
    inventory = await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )
    match = next(
        (g for g in (inventory["envelope"]["data"] or []) if g.get("name") == name),
        None,
    )
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": kind, "name": name},
        normalizer=dependency_graph,
        force=force,
    )
    result["envelope"]["data"] = {
        "object": match,
        "graph": result["envelope"]["data"] or {"nodes": [], "edges": []},
    }
    return result


@router.get("/gitops/{kind}/{name}/timeline")
async def gitops_timeline(kind: str, name: str, sc: Scope = Depends(scope)) -> dict:
    """Reconciliation transitions the engine observed for this object.

    The engine reports a current revision and an applied revision rather than a
    history, so the timeline states exactly what was observed and marks the
    object as lagging when the two disagree (spec sections 78, 261).
    """
    validate_kind(kind)
    validate_name(name)
    inventory = await invoke(
        "gitops.overview",
        sc,
        normalizer=lambda lines, ns: [g.model_dump() for g in normalize_gitops(lines, ns)],
    )
    match = next(
        (g for g in (inventory["envelope"]["data"] or []) if g.get("name") == name),
        None,
    )

    entries: list[dict] = []
    if match:
        desired = str(match.get("revision", ""))
        applied = str(match.get("applied_revision", ""))
        if desired:
            entries.append(
                {
                    "at": "",
                    "event": "Desired revision reported",
                    "revision": desired,
                    "status": match.get("status", "UNKNOWN"),
                    "detail": "from the GitOps object's own status",
                }
            )
        if applied:
            entries.append(
                {
                    "at": "",
                    "event": "Applied revision observed",
                    "revision": applied,
                    "status": "OK" if applied == desired else "WARNING",
                    "detail": "matches the desired revision"
                    if applied == desired
                    else "differs from the desired revision",
                }
            )
        if match.get("suspended"):
            entries.append(
                {
                    "at": "",
                    "event": "Reconciliation suspended",
                    "revision": applied or desired,
                    "status": "NOTICE",
                    "detail": "the object is suspended, so no new revision will be applied",
                }
            )

    lagging = bool(match) and str(match.get("revision", "")) != str(match.get("applied_revision", ""))
    # Every operation route answers with ``{envelope, raw}`` so the UI can show
    # the engine invocation behind the data. This route synthesises the envelope
    # from the overview call, so it carries that call's raw evidence forward.
    envelope = make_envelope(
        {
            "object": match,
            "entries": entries,
            "lagging": lagging,
            "note": (
                "The engine reports the current and applied revision, not a revision history. "
                "Transitions before this observation are not available."
            ),
        },
        context=sc.context,
        namespace=sc.namespace,
        source=(inventory["envelope"].get("source") or "LOCAL"),
        status="WARNING" if lagging else "OK",
    )
    return {"envelope": envelope.model_dump(), "raw": inventory.get("raw")}


@router.get("/gitops/chain")
async def gitops_chain(sc: Scope = Depends(scope)) -> dict:
    """Source → Kustomization → HelmRelease → workload, as a typed graph."""
    return await invoke("graph.gitops", sc, normalizer=dependency_graph)
