"""System / scope / capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import API_SCHEMA_VERSION, SUPERVISION_MODE, WEB_VERSION, settings
from ..models import make_envelope
from ..services import kube
from ..services.cache import cache
from ..services.runner import audit
from ..services.parsers import normalize_capabilities
from ..services.sentinel import adapter
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/system")
async def system_info(sc: Scope = Depends(scope)) -> dict:
    from ..services.evidence import list_incidents

    return make_envelope(
        {
            "webVersion": WEB_VERSION,
            "apiSchema": API_SCHEMA_VERSION,
            "mode": SUPERVISION_MODE,
            "readOnly": True,
            "enginePath": str(settings.engine_path),
            "engineAvailable": settings.engine_available(),
            "bashAvailable": settings.bash_available(),
            "kubeconfig": kube.kubeconfig_path(),
            "incidentId": settings.incident_id,
            "debug": settings.debug,
            "capabilities": kube.capabilities(),
            "operations": [op.model_dump() for op in adapter.operations()],
            "evidenceIncidents": len(list_incidents()),
        },
        context=sc.context,
        namespace=sc.namespace,
        source="LOCAL",
        status="OK",
    ).model_dump()


@router.get("/capabilities")
async def capabilities(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "system.capabilities",
        sc,
        normalizer=lambda lines, ns: [
            c.model_dump() for c in normalize_capabilities(lines)
        ],
    )


@router.get("/contexts")
async def contexts() -> dict:
    data: dict = {"contexts": [], "current": ""}
    errors: list[str] = []
    try:
        data["contexts"] = await kube.list_contexts()
    except kube.KubeError as exc:
        errors.append(str(exc))
    try:
        data["current"] = await kube.current_context()
    except kube.KubeError as exc:
        errors.append(str(exc))
    status = "OK" if data["contexts"] else "UNAVAILABLE"
    return make_envelope(
        data, source="LOCAL", status=status, errors=errors
    ).model_dump()


@router.get("/namespaces")
async def namespaces(
    context: str = Query(""),
    include_system: bool = Query(False),
) -> dict:
    errors: list[str] = []
    try:
        names = await kube.list_namespaces(context)
    except kube.KubeError as exc:
        return make_envelope(
            {"namespaces": []}, context=context, source="UNAVAILABLE",
            status="UNAVAILABLE", errors=[str(exc)],
        ).model_dump()
    if not include_system:
        names = [n for n in names if not n.startswith("kube-")]
    return make_envelope(
        {"namespaces": names}, context=context, source="LOCAL",
        status="OK" if names else "UNKNOWN", errors=errors,
    ).model_dump()


@router.get("/session")
async def session_info(sc: Scope = Depends(scope)) -> dict:
    from ..services.sessions import sessions

    return make_envelope(
        sessions.info(), context=sc.context, namespace=sc.namespace, source="LOCAL"
    ).model_dump()


@router.get("/health")
async def health(sc: Scope = Depends(scope)) -> dict:
    result = await invoke("system.health", sc)
    return result


@router.get("/doctor")
async def doctor(sc: Scope = Depends(scope)) -> dict:
    return await invoke("system.doctor", sc)


@router.get("/profile")
async def profile(sc: Scope = Depends(scope)) -> dict:
    from ..services.parsers import normalize_capabilities

    result = await invoke(
        "system.capabilities", sc, normalizer=lambda lines, ns: [
            c.model_dump() for c in normalize_capabilities(lines)
        ]
    )
    return result


@router.get("/diagnostics")
async def diagnostics() -> dict:
    return make_envelope(
        {"cache": cache.stats(), "audit": audit.recent(50)},
        source="LOCAL",
    ).model_dump()
