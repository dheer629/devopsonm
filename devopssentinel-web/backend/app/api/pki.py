"""PKI / TLS endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..models import make_envelope
from ..security import validate_name
from ..services.parsers import normalize_certificates
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1", tags=["pki"])


def _cert_normalizer(lines: list[str], ns: str) -> list[dict]:
    return [c.model_dump() for c in normalize_certificates(lines, ns)]


@router.get("/certificates")
async def certificates(sc: Scope = Depends(scope)) -> dict:
    return await invoke("pki.certificates", sc, normalizer=_cert_normalizer)


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
    validate_name(name, field="certificate")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Secret", "name": name},
    )


@router.get("/certificates/{name}/chain")
async def chain(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="certificate")
    result = await invoke("pki.certificates", sc, normalizer=_cert_normalizer)
    certs = result["envelope"]["data"] or []
    match = [c for c in certs if c.get("name") == name or c.get("cn") == name]
    result["envelope"]["data"] = {
        "certificate": match[0] if match else None,
        "chain": match,
        "note": "Chain depth is limited to what the engine reported.",
    }
    return result


@router.get("/certificates/{name}/consumers")
async def consumers(name: str, sc: Scope = Depends(scope)) -> dict:
    validate_name(name, field="certificate")
    return await invoke(
        "graph.dependency",
        sc,
        params={"kind": "Secret", "name": name},
    )


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
