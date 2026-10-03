"""Operations endpoints: findings, events, triage, pins, evidence, exports."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ..models import make_envelope
from ..security import validate_incident_id, validate_name
from ..services import evidence as evidence_svc
from ..services.parsers import (
    normalize_events,
    normalize_findings,
    normalize_pods,
)
from ..services.sessions import sessions
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["operations"])


def _findings(lines: list[str], ns: str) -> list[dict]:
    return [f.model_dump() for f in normalize_findings(lines, ns)]


@router.get("/findings")
async def findings(sc: Scope = Depends(scope), force: bool = Query(False)) -> dict:
    return await invoke("workloads.triage", sc, normalizer=_findings, force=force)


@router.get("/triage")
async def triage(sc: Scope = Depends(scope), force: bool = Query(False)) -> dict:
    return await invoke("workloads.triage", sc, force=force)


@router.get("/events")
async def events(sc: Scope = Depends(scope)) -> dict:
    return await invoke(
        "workloads.triage",
        sc,
        normalizer=lambda lines, ns: [e.model_dump() for e in normalize_events(lines, ns)],
    )


@router.get("/snapshot")
async def snapshot(sc: Scope = Depends(scope)) -> dict:
    return await invoke("system.snapshot", sc)


@router.get("/etdp")
async def etdp(sc: Scope = Depends(scope)) -> dict:
    return await invoke("etdp.platform", sc)


@router.get("/database")
async def database(sc: Scope = Depends(scope)) -> dict:
    return await invoke("database.postgres", sc)


@router.get("/kafka")
async def kafka(sc: Scope = Depends(scope)) -> dict:
    return await invoke("kafka.discovery", sc)


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=128),
    sc: Scope = Depends(scope),
) -> dict:
    """Search across the resources the engine can enumerate read-only."""
    needle = q.lower()
    results: list[dict] = []

    resources = await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)],
    )
    for pod in resources["envelope"]["data"] or []:
        if needle in pod.get("name", "").lower():
            results.append(
                {
                    "kind": "Pod",
                    "name": pod["name"],
                    "namespace": pod.get("namespace", ""),
                    "route": f"/workloads/pods/{pod['name']}",
                    "state": pod.get("status", "UNKNOWN"),
                }
            )
    return make_envelope(
        {"query": q, "results": results[:200]},
        context=sc.context,
        namespace=sc.namespace,
        source=resources["envelope"]["source"],
        status="OK" if results else "UNKNOWN",
    ).model_dump()


# --------------------------------------------------------------------------
# Local operator state (pins, history, notes, baselines) -- never secrets.
# --------------------------------------------------------------------------


class PinRequest(BaseModel):
    id: str
    kind: str
    name: str
    context: str = ""
    namespace: str = ""
    health: str = "UNKNOWN"


@router.get("/pins")
async def get_pins() -> dict:
    return make_envelope(sessions.pins(), source="LOCAL").model_dump()


@router.post("/pins")
async def add_pin(payload: PinRequest) -> dict:
    pins = sessions.add_pin(payload.model_dump())
    return make_envelope(pins, source="LOCAL").model_dump()


@router.delete("/pins/{pin_id}")
async def delete_pin(pin_id: str) -> dict:
    return make_envelope(sessions.remove_pin(pin_id), source="LOCAL").model_dump()


@router.get("/history")
async def get_history() -> dict:
    return make_envelope(sessions.history(), source="LOCAL").model_dump()


@router.post("/history")
async def post_history(payload: dict = Body(...)) -> dict:
    sessions.push_history(
        {
            "id": str(payload.get("id", ""))[:200],
            "kind": str(payload.get("kind", ""))[:64],
            "name": str(payload.get("name", ""))[:200],
            "context": str(payload.get("context", ""))[:200],
            "namespace": str(payload.get("namespace", ""))[:200],
        }
    )
    return make_envelope(sessions.history(), source="LOCAL").model_dump()


class NoteRequest(BaseModel):
    incident_id: str
    text: str
    author: str = "operator"


@router.get("/notes/{incident_id}")
async def get_notes(incident_id: str) -> dict:
    validate_incident_id(incident_id)
    return make_envelope(sessions.notes(incident_id), source="LOCAL").model_dump()


@router.post("/notes")
async def add_note(payload: NoteRequest) -> dict:
    validate_incident_id(payload.incident_id)
    notes = sessions.add_note(payload.incident_id, payload.text[:8000], payload.author[:64])
    return make_envelope(notes, source="LOCAL").model_dump()


class BaselineRequest(BaseModel):
    name: str
    context: str = ""
    namespace: str = ""


@router.get("/baselines")
async def get_baselines() -> dict:
    return make_envelope(
        [{k: v for k, v in b.items() if k != "data"} for b in sessions.baselines()],
        source="LOCAL",
    ).model_dump()


@router.post("/baselines")
async def capture_baseline(payload: BaselineRequest, sc: Scope = Depends(scope)) -> dict:
    validate_name(payload.name, field="baseline name")
    captured = await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)],
    )
    entry = sessions.save_baseline(
        payload.name,
        sc.context or payload.context,
        sc.namespace or payload.namespace,
        captured["envelope"]["data"],
    )
    return make_envelope({k: v for k, v in entry.items() if k != "data"}, source="LOCAL").model_dump()


class CompareRequest(BaseModel):
    name: str


@router.post("/baselines/compare")
async def compare_baseline(payload: CompareRequest, sc: Scope = Depends(scope)) -> dict:
    validate_name(payload.name, field="baseline name")
    baseline = sessions.get_baseline(payload.name)
    if baseline is None:
        raise HTTPException(status_code=404, detail="baseline not found")
    current = await invoke(
        "workloads.resources",
        sc,
        normalizer=lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)],
    )
    before = {p["name"]: p for p in (baseline.get("data") or [])}
    after = {p["name"]: p for p in (current["envelope"]["data"] or [])}
    rows: list[dict] = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b is None:
            result = "NEW"
        elif a is None:
            result = "REMOVED"
        elif b.get("status") == a.get("status") and b.get("restarts") == a.get("restarts"):
            result = "UNCHANGED"
        elif a.get("status") == "OK":
            result = "IMPROVED"
        else:
            result = "DEGRADED"
        rows.append(
            {
                "resource": name,
                "pre": {"status": (b or {}).get("status"), "restarts": (b or {}).get("restarts")},
                "post": {"status": (a or {}).get("status"), "restarts": (a or {}).get("restarts")},
                "result": result,
            }
        )
    return make_envelope(
        {"baseline": payload.name, "capturedAt": baseline.get("capturedAt"), "rows": rows},
        context=sc.context,
        namespace=sc.namespace,
        source="LOCAL",
    ).model_dump()


# --------------------------------------------------------------------------
# Evidence center + local exports.
# --------------------------------------------------------------------------


@router.get("/evidence")
async def list_evidence_incidents() -> dict:
    return make_envelope(evidence_svc.list_incidents(), source="LOCAL").model_dump()


@router.get("/evidence/{incident_id}")
async def list_evidence_files(incident_id: str) -> dict:
    validate_incident_id(incident_id)
    return make_envelope(
        evidence_svc.list_evidence(incident_id), source="LOCAL"
    ).model_dump()


@router.get("/evidence/{incident_id}/file")
async def read_evidence_file(incident_id: str, path: str = Query(...)) -> dict:
    validate_incident_id(incident_id)
    try:
        text = evidence_svc.read_evidence(incident_id, path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="evidence file not found") from exc
    return make_envelope(
        {"path": path, "content": text}, source="LOCAL"
    ).model_dump()


@router.get("/exports/{domain}")
async def export_domain(
    domain: str,
    fmt: str = Query("json", pattern="^(json|csv|ndjson|txt)$"),
    sc: Scope = Depends(scope),
) -> Response:
    operation_map = {
        "pods": ("workloads.resources", lambda lines, ns: [p.model_dump() for p in normalize_pods(lines, ns)]),
        "workloads": ("workloads.resources", None),
        "findings": ("workloads.triage", _findings),
        "events": ("workloads.triage", lambda lines, ns: [e.model_dump() for e in normalize_events(lines, ns)]),
    }
    if domain not in operation_map:
        raise HTTPException(status_code=404, detail=f"unknown export domain: {domain}")
    operation_id, normalizer = operation_map[domain]
    result = await invoke(operation_id, sc, normalizer=normalizer)
    filename, media_type, body = evidence_svc.export_payload(
        f"devopssentinel-{domain}", result["envelope"]["data"], fmt
    )
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


