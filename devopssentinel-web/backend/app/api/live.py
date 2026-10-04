"""Opt-in live-data endpoints: read-only SQL console + Kafka topic listing.

Both are **disabled by default** and only exist when the operator explicitly sets
``DSWEB_ENABLE_SQL_CONSOLE=1`` / ``DSWEB_ENABLE_KAFKA_TOPICS=1``. They are the
only code paths in this application that talk to something other than the
DevOpsSentinel engine, and they are documented as such in docs/SECURITY.md.
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..models import make_envelope
from ..services import kafkatool, kube, sqltool

router = APIRouter(prefix="/api/v1", tags=["live"])


def _pg_driver_available() -> bool:
    try:
        import pg8000.dbapi  # noqa: F401
    except ImportError:  # pragma: no cover - depends on environment
        return False
    return True


async def _node_address(context: str) -> str:
    """Best-effort node InternalIP, so the console can prefill a live host.

    A NodePort is reachable on a node address, not on 127.0.0.1 -- inside a
    vcluster only the API port is published to the host. When the cluster
    reports nothing the field stays empty and the browser falls back to its own
    hostname.
    """
    try:
        return await kube.node_address(context)
    except kube.KubeError:
        return ""


@router.get("/database/console")
async def database_console(context: str = Query("")) -> dict:
    """Report whether the read-only SQL console can be used."""
    enabled = settings.enable_sql_console
    driver = _pg_driver_available()
    reason = ""
    if not enabled:
        reason = "disabled: start the backend with DSWEB_ENABLE_SQL_CONSOLE=1"
    elif not driver:
        reason = "the pg8000 driver is not installed on the server"
    return make_envelope(
        {
            "enabled": enabled,
            "driverAvailable": driver,
            "maxRows": settings.sql_max_rows,
            "timeoutS": settings.sql_timeout_s,
            "defaultHost": await _node_address(context),
            "reason": reason,
        },
        source="LOCAL",
        status="OK" if enabled and driver else "UNAVAILABLE",
        warnings=[reason] if reason else [],
    ).model_dump()


class QueryRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=63)
    password: str = Field(default="", max_length=256)
    sql: str = Field(min_length=1, max_length=4000)


@router.post("/database/query")
async def database_query(payload: QueryRequest) -> dict:
    """Run ONE read-only statement. Credentials are never stored or logged."""
    if not settings.enable_sql_console:
        raise HTTPException(
            status_code=403,
            detail="the read-only SQL console is disabled (set DSWEB_ENABLE_SQL_CONSOLE=1)",
        )
    try:
        result = await sqltool.run_query(
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password=payload.password,
            sql=payload.sql,
            timeout=settings.sql_timeout_s,
            max_rows=settings.sql_max_rows,
        )
    except sqltool.SqlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return make_envelope(
        {
            "columns": result.columns,
            "rows": result.rows,
            "rowCount": result.row_count,
            "truncated": result.truncated,
            "target": f"{payload.host}:{payload.port}/{payload.database}",
        },
        source="LIVE",
        duration_ms=result.duration_ms,
    ).model_dump()


@router.get("/kafka/console")
async def kafka_console(context: str = Query("")) -> dict:
    """Report whether Kafka topic listing can be used."""
    enabled = settings.enable_kafka_topics
    reason = "" if enabled else "disabled: start the backend with DSWEB_ENABLE_KAFKA_TOPICS=1"
    return make_envelope(
        {
            "enabled": enabled,
            "timeoutS": settings.kafka_timeout_s,
            "defaultHost": await _node_address(context),
            "reason": reason,
        },
        source="LOCAL",
        status="OK" if enabled else "UNAVAILABLE",
        warnings=[reason] if reason else [],
    ).model_dump()


class TopicsRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9092, ge=1, le=65535)


@router.post("/kafka/topics")
async def kafka_topics(payload: TopicsRequest) -> dict:
    """List topics with a single read-only Kafka Metadata request."""
    if not settings.enable_kafka_topics:
        raise HTTPException(
            status_code=403,
            detail="Kafka topic listing is disabled (set DSWEB_ENABLE_KAFKA_TOPICS=1)",
        )
    try:
        listing = await kafkatool.list_topics(
            payload.host, payload.port, settings.kafka_timeout_s
        )
    except kafkatool.KafkaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return make_envelope(
        {
            "bootstrap": listing.bootstrap,
            "brokers": listing.brokers,
            "topics": [dataclasses.asdict(topic) for topic in listing.topics],
            "truncated": listing.truncated,
        },
        source="LIVE",
        duration_ms=listing.duration_ms,
    ).model_dump()
