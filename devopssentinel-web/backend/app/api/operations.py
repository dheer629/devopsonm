"""Operations endpoints: findings, events, triage, pins, evidence, exports."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ..models import make_envelope
from ..security import validate_incident_id, validate_name
from ..services import evidence as evidence_svc
from ..services.parsers import (
    normalize_certificates,
    normalize_db_services,
    normalize_events,
    normalize_findings,
    normalize_gitops,
    normalize_kafka_services,
    normalize_pods,
    normalize_pvcs,
    normalize_services,
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
async def events(sc: Scope = Depends(scope), force: bool = Query(False)) -> dict:
    """Namespace events.

    Preferred path is one bounded read-only ``kubectl get events -o json``: it
    works as soon as a connection is active and costs a single API call. The
    engine's triage report stays as the fallback, so an engine-only deployment
    still returns data.

    Both paths must answer with the same ``{envelope, raw, exitStatus}`` shape.
    The browser reads ``envelope``, so returning a bare envelope here made the
    page throw on ``.envelope.data`` whenever the live path won -- which is the
    normal case, and why the fixture-backed E2E suite never saw it.
    """
    from ..services import kube
    from ..services.parsers import normalize_live_events

    warnings: list[str] = []
    started = time.perf_counter()
    try:
        rows, stdout = await kube.events_with_raw(
            context=sc.context, namespace=sc.namespace
        )
    except kube.KubeError as exc:
        rows, stdout = [], ""
        warnings.append(str(exc))
    if rows:
        duration_ms = int((time.perf_counter() - started) * 1000)
        argv = kube.events_argv(context=sc.context, namespace=sc.namespace)
        envelope = make_envelope(
            [e.model_dump() for e in normalize_live_events(rows, sc.namespace)],
            context=sc.context,
            namespace=sc.namespace,
            source="LIVE",
            status="OK",
            duration_ms=duration_ms,
            warnings=warnings,
        )
        return {
            "envelope": envelope.model_dump(),
            "raw": {
                "engineArgv": ["kubectl", *argv],
                "readOnlyCommand": kube.command_string(argv),
                "exitStatus": 0,
                "stdout": stdout,
                "stderr": "",
                "durationMs": duration_ms,
            },
            "exitStatus": 0,
        }

    result = await invoke(
        "workloads.triage",
        sc,
        normalizer=lambda lines, ns: [e.model_dump() for e in normalize_events(lines, ns)],
        force=force,
    )
    if warnings:
        envelope = result.get("envelope") or {}
        envelope["warnings"] = [*envelope.get("warnings", []), *warnings]
    return result


@router.get("/snapshot")
async def snapshot(sc: Scope = Depends(scope)) -> dict:
    return await invoke("system.snapshot", sc)


@router.get("/application-profile")
async def application_profile(sc: Scope = Depends(scope)) -> dict:
    return await invoke("application.profile", sc)


@router.get("/database")
async def database(sc: Scope = Depends(scope)) -> dict:
    return await invoke("database.postgres", sc)


@router.get("/database/services")
async def database_services(sc: Scope = Depends(scope)) -> dict:
    """Structured view of the discovered database Services (metadata only)."""
    return await invoke(
        "database.postgres",
        sc,
        normalizer=lambda lines, ns: [
            d.model_dump() for d in normalize_db_services(lines, ns)
        ],
    )


@router.get("/kafka")
async def kafka(sc: Scope = Depends(scope)) -> dict:
    return await invoke("kafka.discovery", sc)


@router.get("/kafka/services")
async def kafka_services(sc: Scope = Depends(scope)) -> dict:
    """Structured view of the discovered Kafka broker Services + bootstrap."""
    return await invoke(
        "kafka.discovery",
        sc,
        normalizer=lambda lines, ns: [
            k.model_dump() for k in normalize_kafka_services(lines, ns)
        ],
    )


# --------------------------------------------------------------------------
# Global search (spec 11-12): one query across every domain the engine can
# enumerate read-only. This reuses the engine operations the domain pages
# already call -- it adds no Kubernetes logic of its own.
# --------------------------------------------------------------------------

# kind prefix -> canonical result kind
_PREFIX_KINDS: dict[str, str] = {
    "pod": "Pod",
    "pods": "Pod",
    "svc": "Service",
    "service": "Service",
    "services": "Service",
    "cert": "Certificate",
    "certs": "Certificate",
    "certificate": "Certificate",
    "certificates": "Certificate",
    "gitops": "GitOps",
    "flux": "GitOps",
    "helm": "GitOps",
    "pvc": "PVC",
    "storage": "PVC",
    "finding": "Finding",
    "findings": "Finding",
}

# The state field each domain reports, in priority order.
_STATE_KEYS = ("status", "state", "severity", "health", "ready")


def _parse_search_query(raw: str) -> tuple[list[str], dict[str, str]]:
    """Split ``status:failed ns:payments transformer`` into terms + filters."""
    terms: list[str] = []
    filters: dict[str, str] = {}
    for token in raw.split():
        key, sep, value = token.partition(":")
        if sep:
            key = key.lower()
            if key in _PREFIX_KINDS:
                # A bare `cert:` means "every certificate", not a search for
                # the literal text `cert:`.
                filters["kind"] = _PREFIX_KINDS[key]
                if value:
                    terms.append(value.lower())
                continue
            if value and key in ("ns", "namespace"):
                filters["namespace"] = value.lower()
                continue
            if value and key in ("status", "state"):
                filters["state"] = value.lower()
                continue
        terms.append(token.lower())
    return terms, filters


def _search_row_state(row: dict) -> str:
    for key in _STATE_KEYS:
        value = row.get(key)
        if isinstance(value, bool):
            return "OK" if value else "FAILED"
        if value:
            return str(value).upper()
    return "UNKNOWN"


def _row_matches(row: dict, terms: list[str], filters: dict[str, str]) -> bool:
    if filters.get("kind") and row["kind"] != filters["kind"]:
        return False
    if filters.get("namespace") and filters["namespace"] not in row["namespace"].lower():
        return False
    if filters.get("state") and filters["state"] not in row["state"].lower():
        return False
    if not terms:
        return True
    haystack = f"{row['name']} {row['namespace']}".lower()
    # Lower-case defensively: the parser already normalises, but a direct
    # caller must not have to know that.
    return all(term.lower() in haystack for term in terms)


async def _search_domain(
    spec_id: str,
    normalizer,
    kind: str,
    route: str,
    sc: Scope,
) -> tuple[list[dict], str]:
    """Run one engine operation and shape its rows as search results.

    Returns ``(rows, source)`` where source is the engine's own provenance
    (``LIVE``/``CACHE``/``UNAVAILABLE``) so the UI can attribute each hit.
    """

    def _rows(lines: list[str], ns: str) -> list[dict]:
        return [row.model_dump() for row in normalizer(lines, ns)]

    result = await invoke(spec_id, sc, normalizer=_rows)
    envelope = result.get("envelope") or {}
    rows: list[dict] = []
    for row in envelope.get("data") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        rows.append(
            {
                "kind": kind,
                "name": str(row.get("name", "")),
                "namespace": str(row.get("namespace", "") or sc.namespace),
                "route": route.format(name=row.get("name", "")),
                "state": _search_row_state(row),
                "source": str(envelope.get("source", "UNAVAILABLE")),
                "engine": spec_id,
            }
        )
    return rows, str(envelope.get("source", "UNAVAILABLE"))


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=128),
    sc: Scope = Depends(scope),
) -> dict:
    """Search every enumerable domain in one query.

    Supports the prefix grammar from the spec: ``pod:``, ``svc:``, ``cert:``,
    ``gitops:``, ``pvc:``, ``finding:`` select a kind, ``ns:`` a namespace and
    ``status:`` a state. Plain terms match case-insensitively against name and
    namespace, so an exact Kubernetes name is never required.

    Domains are queried concurrently and the engine's TTL cache de-duplicates
    repeat work, so a re-typed query costs nothing.
    """
    terms, filters = _parse_search_query(q)

    domains = (
        ("workloads.resources", normalize_pods, "Pod", "/workloads/pods/{name}"),
        ("network.topology", normalize_services, "Service", "/network?name={name}"),
        ("pki.certificates", normalize_certificates, "Certificate", "/pki?name={name}"),
        ("gitops.overview", normalize_gitops, "GitOps", "/gitops?name={name}"),
        ("storage.dependencies", normalize_pvcs, "PVC", "/storage?name={name}"),
        ("workloads.triage", normalize_findings, "Finding", "/findings?name={name}"),
    )
    wanted = filters.get("kind")
    selected = [d for d in domains if wanted is None or d[2] == wanted]

    gathered = await asyncio.gather(
        *(_search_domain(spec_id, norm, kind, route, sc) for spec_id, norm, kind, route in selected),
        return_exceptions=True,
    )

    results: list[dict] = []
    sources: list[str] = []
    unavailable: list[str] = []
    for entry, (_spec_id, _norm, kind, _route) in zip(gathered, selected, strict=True):
        if isinstance(entry, BaseException):
            unavailable.append(kind)
            continue
        rows, source = entry
        sources.append(source)
        results.extend(row for row in rows if _row_matches(row, terms, filters))

    results.sort(key=lambda row: (row["kind"], row["name"]))
    if "LIVE" in sources:
        source = "LIVE"
    elif sources:
        source = sources[0]
    else:
        source = "UNAVAILABLE"

    return make_envelope(
        {
            "query": q,
            "terms": terms,
            "filters": filters,
            "results": results[:200],
            "total": len(results),
            "searched": [kind for _s, _n, kind, _r in selected],
            "unavailable": unavailable,
        },
        context=sc.context,
        namespace=sc.namespace,
        source=source,
        status="OK" if results else "UNKNOWN",
        warnings=[f"{kind} search was unavailable" for kind in unavailable],
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


