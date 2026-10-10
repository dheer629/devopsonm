"""PKI / TLS endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..models import make_envelope
from ..security import validate_name
from ..services.parsers import (
    normalize_certificates,
    normalize_dependency_graph,
    normalize_secrets,
)
from .deps import Scope, invoke, scope
from .graph import reverse_dependency_result

router = APIRouter(prefix="/api/v1", tags=["pki"])


def _cert_normalizer(lines: list[str], ns: str) -> list[dict]:
    return [c.model_dump() for c in normalize_certificates(lines, ns)]


def _secret_normalizer(lines: list[str], ns: str) -> list[dict]:
    return [s.model_dump() for s in normalize_secrets(lines, ns)]


def _graph_normalizer(lines: list[str], _ns: str) -> dict:
    return normalize_dependency_graph(lines).model_dump()


@router.get("/certificates")
async def certificates(sc: Scope = Depends(scope)) -> dict:
    return await invoke("pki.certificates", sc, normalizer=_cert_normalizer)


@router.get("/secrets")
async def secrets(sc: Scope = Depends(scope)) -> dict:
    """Secret inventory with derived TLS certificate expiry (metadata only)."""
    return await invoke("pki.certificates", sc, normalizer=_secret_normalizer)


@router.get("/certificates/expiry")
async def expiry(sc: Scope = Depends(scope)) -> dict:
    return await invoke("pki.cert_expiry", sc, normalizer=_cert_normalizer)


@router.get("/certificates/duplicates")
async def duplicates(sc: Scope = Depends(scope)) -> dict:
    result = await invoke("pki.certificates", sc, normalizer=_cert_normalizer)
    certs = result["envelope"]["data"] or []
    seen: dict[str, list[str]] = {}
    for cert in certs:
        key = cert.get("cn") or cert.get("name")
        seen.setdefault(key, []).append(cert.get("name"))
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    result["envelope"]["data"] = dupes
    return result


@router.get("/certificates/issuers")
async def issuers(sc: Scope = Depends(scope)) -> dict:
    result = await invoke("pki.certificates", sc, normalizer=_cert_normalizer)
    certs = result["envelope"]["data"] or []
    issuers = sorted({c.get("issuer", "") for c in certs if c.get("issuer")})
    result["envelope"]["data"] = issuers
    return result


@router.get("/certificates/{name}")
async def certificate(name: str, sc: Scope = Depends(scope)) -> dict:
    """One certificate's dependency neighbourhood, as a typed graph.

    The certificate itself is looked up in the inventory so the detail view can
    show validity and issuer alongside the relationships.
    """
    validate_name(name, field="certificate")
    inventory = await invoke("pki.certificates", sc, normalizer=_cert_normalizer)
    certs = inventory["envelope"]["data"] or []
    match = next(
        (c for c in certs if c.get("name") == name or c.get("cn") == name),
        None,
    )
    result = await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Secret", "name": name},
        normalizer=_graph_normalizer,
    )
    result["envelope"]["data"] = {
        "certificate": match,
        "graph": result["envelope"]["data"] or {"nodes": [], "edges": []},
    }
    if match is None:
        result["envelope"]["warnings"] = [
            *result["envelope"].get("warnings", []),
            "this name is not in the certificate inventory; showing relationships only",
        ]
    return result


@router.get("/certificates/{name}/chain")
async def chain(name: str, sc: Scope = Depends(scope)) -> dict:
    """Leaf → intermediate → root, limited to what the engine reported.

    The engine reports issuer relationships rather than a parsed PKI chain, so
    depth is whatever it observed. We never synthesise missing links.
    """
    validate_name(name, field="certificate")
    result = await invoke("pki.certificates", sc, normalizer=_cert_normalizer)
    certs = result["envelope"]["data"] or []
    match = [c for c in certs if c.get("name") == name or c.get("cn") == name]
    leaf = match[0] if match else None

    # Walk the issuer names the inventory already carries. A cycle guard keeps a
    # self-signed or mis-reported issuer from looping forever.
    root_markers = ("", "unknown", "self", "self-signed")
    links: list[dict] = []
    seen: set[str] = set()
    cursor = leaf
    terminated = "not-in-inventory"
    while cursor is not None:
        seen.add(str(cursor.get("cn") or cursor.get("name") or ""))
        issuer = str(cursor.get("issuer", "")).strip()
        links.append(
            {
                "subject": cursor.get("cn") or cursor.get("name"),
                "issuer": issuer or "unknown",
                "expiry": cursor.get("expiry", ""),
                "days": cursor.get("days"),
                "status": cursor.get("status", "UNKNOWN"),
                "serial": cursor.get("serial", ""),
            }
        )
        if not issuer or issuer.lower() in root_markers:
            terminated = "root"
            break
        if issuer in seen:
            terminated = "cycle"
            break
        seen.add(issuer)
        cursor = next(
            (c for c in certs if c.get("cn") == issuer or c.get("name") == issuer),
            None,
        )

    result["envelope"]["data"] = {
        "certificate": leaf,
        "chain": links,
        "depth": len(links),
        # ``complete`` is only true when the walk reached a self-signed or
        # unknown root. Stopping because the issuer is not in the inventory
        # means the chain is truncated, not finished.
        "complete": terminated == "root",
        "terminated": terminated,
        "note": "Chain depth is limited to what the engine reported.",
    }
    return result


@router.get("/certificates/{name}/consumers")
async def consumers(name: str, sc: Scope = Depends(scope)) -> dict:
    """Objects that reference this certificate (reverse dependencies)."""
    validate_name(name, field="certificate")
    return await reverse_dependency_result("Secret", name, sc)


class TlsInspectRequest(BaseModel):
    host: str
    port: int = 443
    server_name: str | None = None


@router.post("/tls/inspect")
async def tls_inspect(payload: TlsInspectRequest) -> dict:
    """Live TLS inspection is CLI-only in the engine.

    We deliberately do NOT open arbitrary sockets from the browser-supplied
    host. The endpoint returns an explicit UNAVAILABLE so the UI can gate it.
    """
    return make_envelope(
        {"host": payload.host, "port": payload.port},
        source="UNAVAILABLE",
        status="UNAVAILABLE",
        warnings=[
            "Live TLS inspection runs only in the engine's interactive console; "
            "the browser adapter does not open arbitrary TLS connections."
        ],
    ).model_dump()
