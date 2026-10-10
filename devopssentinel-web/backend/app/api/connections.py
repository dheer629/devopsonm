"""Cluster connection endpoints.

Read-only discovery plus an explicit, operator-driven activation. Nothing here
mutates a cluster; the only side effect is the local connection preference under
the private state directory.
"""

from __future__ import annotations

import asyncio
import re
import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..models import make_envelope
from ..services import connections, discovery, liveconfig
from ..services.connections import ConnectionError

router = APIRouter(prefix="/api/v1", tags=["connections"])

# An API server that only a host process can reach.
_LOOPBACK_SERVER = re.compile(
    r"^(?:https?://)?(?:localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(?::\d+)?/?$",
    re.IGNORECASE,
)


def _unreachable_warning(conn: connections.ActiveConnection) -> list[str]:
    """Warn when the active context names a host-local API server.

    vcluster writes ``https://localhost:10093`` into the kubeconfig because
    that is the port-forward ``vcluster connect`` opens on the workstation.
    Inside a container ``localhost`` is the container itself, so the connection
    saves cleanly, reports itself as configured, and then fails on every page.
    """
    if conn.server_override or not conn.server:
        return []
    if not _LOOPBACK_SERVER.match(conn.server):
        return []
    return [
        f"the kubeconfig points at {conn.server}, which inside a container is "
        "the container itself, not the Docker host. Set an API server override "
        "to the cluster's published host port (for example "
        "https://host.docker.internal:11259) and activate again, or press "
        "Connect on a detected cluster."
    ]


def _unreachable_warning_from(row: dict | None) -> list[str]:
    """The same warning for a plain connection dict, as returned on the wire."""
    if not row:
        return []
    conn = connections.ActiveConnection(
        candidate_id=str(row.get("candidate_id", "")),
        kubeconfig=str(row.get("kubeconfig", "")),
        context=str(row.get("context", "")),
        namespace=str(row.get("namespace", "")),
        server_override=str(row.get("server_override", "")),
        insecure_skip_tls_verify=bool(row.get("insecure_skip_tls_verify", False)),
        environment=str(row.get("environment", "UNKNOWN")),
        label=str(row.get("label", "")),
        server=str(row.get("server", "")),
    )
    return _unreachable_warning(conn)


def _camel(key: str) -> str:
    """``server_override`` -> ``serverOverride``."""
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest if part)


def _camel_row(row: dict) -> dict:
    """camelCase a service dataclass dump so it matches the TypeScript types.

    The connection service returns dataclasses whose field names are snake_case,
    while the browser client is written against camelCase interfaces. Renaming
    here, at the wire boundary, keeps one convention per side instead of leaving
    fields such as ``effectiveKubeconfig`` permanently undefined in the UI.
    """
    out: dict = {}
    for key, value in row.items():
        if isinstance(value, dict):
            value = _camel_row(value)
        out[_camel(key)] = value
    return out


def _files() -> list[dict]:
    rows: list[dict] = []
    for source, path in connections.discover_kubeconfig_files():
        try:
            size = path.stat().st_size
        except OSError:  # pragma: no cover - defensive
            size = 0
        rows.append({"source": source, "path": str(path), "bytes": size})
    return rows


@router.get("/connections")
async def list_connections() -> dict:
    """Discovered kubeconfigs, every context in them, and the active choice.

    ``health`` answers the question Settings otherwise gets wrong: is the active
    connection *usable*, not merely configured? A vcluster's published port
    changes when it restarts, so a pinned override can go stale while the saved
    configuration still looks complete.
    """
    candidates = await asyncio.to_thread(connections.discover_candidates)
    active = connections.load_active()
    health = await asyncio.to_thread(connections.check_active) if active else None
    return make_envelope(
        {
            "files": _files(),
            "candidates": [_camel_row(c.as_dict()) for c in candidates],
            "active": _camel_row(active.as_dict()) if active else None,
            "health": health,
            "kubectlAvailable": bool(shutil.which("kubectl")),
            "effectiveKubeconfig": connections.active_kubeconfig(),
            "stateDir": str(settings.state_dir),
            "live": liveconfig.snapshot(),
        },
        source="LOCAL",
        status="OK" if candidates else "UNAVAILABLE",
        warnings=[] if candidates else ["no kubeconfig was found on the server"],
    ).model_dump()


class ProbeRequest(BaseModel):
    candidateId: str = Field(default="", max_length=64)
    kubeconfig: str = Field(default="", max_length=4096)
    context: str = Field(default="", max_length=253)
    serverOverride: str = Field(default="", max_length=2048)
    insecureSkipTlsVerify: bool = False


@router.post("/connections/probe")
async def probe_connection(payload: ProbeRequest) -> dict:
    """Test one connection before committing to it."""
    kubeconfig = payload.kubeconfig
    context = payload.context
    if payload.candidateId:
        candidate = await asyncio.to_thread(connections.find_candidate, payload.candidateId)
        if candidate is None:
            raise HTTPException(status_code=404, detail="unknown connection")
        kubeconfig, context = candidate.kubeconfig, candidate.context
    if not kubeconfig or not context:
        raise HTTPException(status_code=400, detail="a kubeconfig and context are required")
    result = await asyncio.to_thread(
        connections.probe,
        kubeconfig=kubeconfig,
        context=context,
        server_override=payload.serverOverride,
        insecure_skip_tls_verify=payload.insecureSkipTlsVerify,
    )
    return make_envelope(
        _camel_row(result.as_dict()),
        context=context,
        source="LIVE" if result.reachable else "UNAVAILABLE",
        status="OK" if result.reachable else "FAILED",
        errors=[] if result.reachable else [result.detail or result.status],
    ).model_dump()


class ActivateRequest(BaseModel):
    candidateId: str = Field(min_length=1, max_length=64)
    namespace: str = Field(default="", max_length=253)
    serverOverride: str = Field(default="", max_length=2048)
    insecureSkipTlsVerify: bool = False


@router.post("/connections/activate")
async def activate_connection(payload: ActivateRequest) -> dict:
    """Persist one connection as the cluster the whole application uses."""
    try:
        conn = await asyncio.to_thread(
            connections.activate,
            payload.candidateId,
            namespace=payload.namespace,
            server_override=payload.serverOverride,
            insecure_skip_tls_verify=payload.insecureSkipTlsVerify,
        )
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return make_envelope(
        _camel_row(conn.as_dict()),
        context=conn.context,
        namespace=conn.namespace,
        source="LOCAL",
        warnings=_unreachable_warning(conn),
    ).model_dump()


@router.post("/connections/deactivate")
async def deactivate_connection() -> dict:
    await asyncio.to_thread(connections.deactivate)
    return make_envelope({"active": None}, source="LOCAL").model_dump()


class AutoRequest(BaseModel):
    # Reconnect even when a connection is already active and healthy.
    force: bool = False


@router.post("/connections/auto")
async def auto_connection(payload: AutoRequest | None = None) -> dict:
    """Detect a reachable cluster and activate it, with no operator input.

    This is the one-click container path and the one the console calls on load.
    It pairs discovered API endpoints with discovered credentials, so a vcluster
    whose kubeconfig names a host port-forward is still found. An already-working
    connection is left alone unless ``force`` is set.
    """
    force = bool(payload.force) if payload else False
    health = await asyncio.to_thread(connections.check_active)
    if health.get("reachable") and not force:
        return make_envelope(
            {
                "activated": None,
                "attempts": [],
                "reason": "ALREADY_CONNECTED",
                "advice": "",
                "serverOverride": health.get("server", ""),
                "detected": None,
                "serverVersion": health.get("serverVersion", ""),
                "health": health,
            },
            context=health.get("context", ""),
            source="LIVE",
            status="OK",
        ).model_dump()

    report = await asyncio.to_thread(connections.auto_connect)
    activated = report.get("activated")
    health = await asyncio.to_thread(connections.check_active)
    # Report the real cause per pairing attempt. A single canned string ("no
    # kubeconfig could authenticate") is actively misleading: a mounted
    # kubeconfig that a *different* API server on the same host rejects with 401
    # looks identical to having no kubeconfig at all.
    errors: list[str] = []
    if not activated:
        for attempt in report.get("attempts") or []:
            errors.append(
                f"{attempt.get('context') or 'context'} @ "
                f"{attempt.get('server') or 'kubeconfig server'}: "
                f"{attempt.get('reason') or 'FAILED'} - "
                f"{attempt.get('detail') or 'no detail reported'}"
            )
        if not errors:
            errors.append(report.get("advice") or "no reachable cluster was found")
    return make_envelope(
        {
            "activated": _camel_row(activated) if activated else None,
            "attempts": [_camel_row(row) for row in report.get("attempts") or []],
            "reason": report.get("reason", ""),
            "advice": report.get("advice", ""),
            "serverOverride": report.get("serverOverride", ""),
            "detected": _camel_row(report["detected"]) if report.get("detected") else None,
            "serverVersion": report.get("serverVersion", ""),
            "health": health,
        },
        context=(activated or {}).get("context", ""),
        source="LIVE" if activated else "UNAVAILABLE",
        status="OK" if activated else "FAILED",
        warnings=_unreachable_warning_from(activated) if activated else [],
        errors=errors,
    ).model_dump()


class ImportRequest(BaseModel):
    name: str = Field(default="imported", max_length=40)
    content: str = Field(min_length=16, max_length=1_000_000)


@router.post("/connections/import")
async def import_connection(payload: ImportRequest) -> dict:
    """Accept a pasted kubeconfig and return the contexts it contains."""
    try:
        rows = await asyncio.to_thread(connections.import_kubeconfig, payload.content, payload.name)
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return make_envelope(
        {"candidates": [c.as_dict() for c in rows]}, source="LOCAL"
    ).model_dump()


@router.get("/connections/discover")
async def discover_endpoints() -> dict:
    """Find Kubernetes API servers a container can actually reach.

    Two sources are combined: the Docker socket (when mounted read-only), which
    names the vcluster/kind/k3s/minikube container and its published ports, and
    a sweep of well-known API ports on the Docker host aliases. Every candidate
    is proven with an unauthenticated ``/version`` call, so a result is evidence
    rather than a guess.
    """
    result = await asyncio.to_thread(discovery.discover_endpoints)
    return make_envelope(
        result,
        source="LIVE" if result["endpoints"] else "UNAVAILABLE",
        status="OK" if result["endpoints"] else "UNAVAILABLE",
        warnings=[]
        if result["dockerAvailable"]
        else [
            "the Docker socket is not mounted, so container-level discovery is "
            "limited to a port sweep (mount /var/run/docker.sock:ro to enable it)"
        ],
    ).model_dump()


class PairRequest(BaseModel):
    server: str = Field(min_length=8, max_length=2048)


@router.post("/connections/pair")
async def pair_connection(payload: PairRequest) -> dict:
    """Pair a discovered API endpoint with the kubeconfig that opens it.

    One click for the container case: discovery finds the port, this finds the
    credentials, and the result becomes the active connection.
    """
    result = await asyncio.to_thread(connections.pair_and_activate, payload.server)
    activated = result.get("activated")
    # Report the real cause per kubeconfig. The previous single canned string
    # ("no kubeconfig could authenticate") was actively misleading: a mounted
    # kubeconfig that is rejected with 401 by a *different* API server on the
    # same host looked identical to having no kubeconfig at all.
    errors: list[str] = []
    if not activated:
        for attempt in result.get("attempts") or []:
            errors.append(
                f"{attempt.get('context') or 'context'}: "
                f"{attempt.get('reason') or 'FAILED'} - "
                f"{attempt.get('detail') or 'no detail reported'}"
            )
        if not errors:
            errors.append(
                result.get("advice")
                or "no kubeconfig on the server could authenticate against that endpoint"
            )
    return make_envelope(
        {
            "activated": _camel_row(activated) if activated else None,
            "attempts": [_camel_row(a) for a in result.get("attempts") or []],
            "reason": result.get("reason", ""),
            "advice": result.get("advice", ""),
        },
        context=(activated or {}).get("context", ""),
        source="LIVE" if activated else "UNAVAILABLE",
        status="OK" if activated else "FAILED",
        errors=errors,
    ).model_dump()


# ------------------------------------------------------------ settings view


@router.get("/settings")
async def read_settings() -> dict:
    """One document the Settings page reads: connection plus live features."""
    active = connections.load_active()
    return make_envelope(
        {
            "connection": _camel_row(active.as_dict()) if active else None,
            "effectiveKubeconfig": connections.active_kubeconfig(),
            "live": liveconfig.snapshot(),
            "kubectlAvailable": bool(shutil.which("kubectl")),
            "stateDir": str(settings.state_dir),
            "files": _files(),
        },
        context=active.context if active else "",
        namespace=active.namespace if active else "",
        source="LOCAL",
    ).model_dump()


class LiveSettingsRequest(BaseModel):
    sqlConsole: bool | None = None
    kafkaTopics: bool | None = None


@router.post("/settings/live")
async def write_live_settings(payload: LiveSettingsRequest) -> dict:
    """Turn the two opt-in live-data features on or off without a restart."""
    flags = liveconfig.set_flags(
        sql_console=payload.sqlConsole, kafka_topics=payload.kafkaTopics
    )
    return make_envelope(flags, source="LOCAL").model_dump()
