"""Opt-in, read-only SQL console.

This is the one deliberate exception to "only the engine talks to the cluster".
It exists because the engine exposes PostgreSQL read-only sessions only in its
interactive console, and the operator asked for the same checks in the browser.

Guarantees (see docs/SECURITY.md):
  * disabled unless ``DSWEB_ENABLE_SQL_CONSOLE=1``
  * credentials are used in memory for a single request and are never logged,
    audited, stored or echoed back
  * the statement is validated against a strict read-only allowlist; it is never
    placed in a subprocess argv
  * the database session is forced read-only **server-side**
    (``SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY``), so even a
    validation bypass cannot mutate data
  * bounded by a statement timeout, a wall-clock timeout and a row cap
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..security import redact_text
from .runner import AuditRecord, audit


class SqlError(RuntimeError):
    """Raised with a safe, user-facing message."""


_ALLOWED_PREFIX = re.compile(
    r"^(select|with|show|explain|table|values|\\d|\\l|\\dt|\\dv|\\dn|\\df)\b",
    re.IGNORECASE,
)

# Rejected anywhere outside string literals / comments.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|analyze|reindex|refresh|call|do|begin|commit|rollback|savepoint|"
    r"set|reset|listen|notify|unlisten|merge|import|lock|cluster|discard|"
    r"reassign|prepare|execute|deallocate|declare|fetch|move)\b",
    re.IGNORECASE,
)

_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_LITERAL = re.compile(r"'(?:[^']|'')*'")
_DOLLAR = re.compile(r"\$\$.*?\$\$", re.DOTALL)

_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._:-]{0,252}[A-Za-z0-9])?$")
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_$.-]{0,62}$")


def _bare(sql: str) -> str:
    """Strip comments and literals so keyword checks cannot be fooled."""
    out = _COMMENT.sub(" ", sql)
    out = _LITERAL.sub("''", out)
    return _DOLLAR.sub("$$$$", out)


def validate_sql(sql: str) -> str:
    """Return the statement to execute, or raise :class:`SqlError`."""
    text = (sql or "").strip()
    if not text:
        raise SqlError("empty statement")
    if len(text) > 4000:
        raise SqlError("statement too long (max 4000 characters)")
    bare = _bare(text).rstrip().rstrip(";").strip()
    if ";" in bare:
        raise SqlError("only one statement per request is allowed")
    if not _ALLOWED_PREFIX.match(bare):
        raise SqlError(
            "only read-only statements are allowed: SELECT, WITH, SHOW, EXPLAIN, "
            "TABLE, VALUES or a \\d meta-command"
        )
    hit = _FORBIDDEN.search(bare)
    if hit:
        raise SqlError(f"statement contains a non read-only keyword: {hit.group(0).upper()}")
    return text.rstrip().rstrip(";")


def _safe(message: object) -> str:
    return redact_text(str(message)).replace("\n", " ")[:300]


def validate_target(host: str, port: int, database: str, username: str) -> None:
    if not host or not _HOST.match(host) or host.startswith("-"):
        raise SqlError("invalid host")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise SqlError("invalid port")
    if not database or not _NAME.match(database):
        raise SqlError("invalid database name")
    if not username or not _NAME.match(username):
        raise SqlError("invalid username")


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int = 0


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def _run_blocking(
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    sql: str,
    timeout: float,
    max_rows: int,
) -> QueryResult:
    try:
        import pg8000.dbapi as pg  # imported lazily: optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SqlError("the pg8000 driver is not installed on the server") from exc

    started = time.monotonic()
    try:
        connection = pg.connect(
            user=username,
            password=password,
            host=host,
            port=port,
            database=database,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - the driver raises many types
        raise SqlError(f"connection failed: {_safe(exc)}") from exc

    try:
        connection.autocommit = True
        cursor = connection.cursor()
        # Server-side read-only: even a validation bypass cannot mutate data.
        cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        cursor.execute(f"SET statement_timeout = {int(timeout * 1000)}")
        cursor.execute(sql)
        columns: list[str] = []
        rows: list[list[Any]] = []
        if cursor.description:
            columns = [str(column[0]) for column in cursor.description]
            fetched = cursor.fetchmany(max_rows)
            rows = [[_jsonable(value) for value in row] for row in fetched]
        truncated = len(rows) == max_rows
    except Exception as exc:  # noqa: BLE001
        raise SqlError(f"query failed: {_safe(exc)}") from exc
    finally:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 - best effort
            pass

    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _audit(host: str, port: int, database: str, duration_ms: int, status: int, rows: int) -> None:
    """Record the target and row count -- never the credentials or the SQL."""
    audit.add(
        AuditRecord(
            timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            operation="database.query",
            context=f"{host}:{port}/{database}",
            namespace="",
            duration_ms=duration_ms,
            exit_status=status,
            record_count=rows,
            source="SQL",
        )
    )


async def run_query(
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    sql: str,
    timeout: float,
    max_rows: int,
) -> QueryResult:
    validate_target(host, port, database, username)
    statement = validate_sql(sql)
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_blocking,
                host=host,
                port=port,
                database=database,
                username=username,
                password=password,
                sql=statement,
                timeout=timeout,
                max_rows=max_rows,
            ),
            timeout=timeout + 5,
        )
    except asyncio.TimeoutError as exc:
        _audit(host, port, database, int((time.monotonic() - started) * 1000), 124, 0)
        raise SqlError(f"query exceeded the {timeout:.0f}s limit") from exc

    _audit(host, port, database, result.duration_ms, 0, result.row_count)
    return result

