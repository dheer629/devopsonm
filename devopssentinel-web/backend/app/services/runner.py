"""Bounded, read-only subprocess execution.

Guarantees (spec sections 6, 62, 81):
  * argv arrays only -- never ``shell=True``
  * read-only guard rejects mutation verbs
  * hard timeout with child cancellation
  * output size cap
  * every call recorded in an audit trail
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from ..config import settings
from ..security import assert_read_only, redact_text
from . import connections


@dataclass
class RunResult:
    argv: list[str]
    exit_status: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False
    error: str = ""

    @property
    def read_only_command(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


@dataclass
class AuditRecord:
    timestamp: str
    operation: str
    context: str
    namespace: str
    duration_ms: int
    exit_status: int
    record_count: int
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "context": self.context,
            "namespace": self.namespace,
            "durationMs": self.duration_ms,
            "exitStatus": self.exit_status,
            "recordCount": self.record_count,
            "source": self.source,
        }


@dataclass
class AuditTrail:
    records: list[AuditRecord] = field(default_factory=list)
    max_records: int = 500

    def add(self, record: AuditRecord) -> None:
        self.records.append(record)
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]

    def recent(self, limit: int = 100) -> list[dict[str, object]]:
        return [r.as_dict() for r in self.records[-limit:]][::-1]


audit = AuditTrail()


def _terminate(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.terminate()
    except ProcessLookupError:  # pragma: no cover
        pass


def _count_records(stdout: str) -> int:
    return sum(1 for line in stdout.splitlines() if line.strip())


class Runner:
    """Executes the DevOpsSentinel engine with hard safety bounds."""

    def __init__(self, engine_path=None, bash_binary: str | None = None) -> None:
        self.engine_path = engine_path or settings.engine_path
        self.bash_binary = bash_binary or settings.bash_binary

    def build_argv(self, engine_args: Sequence[str]) -> list[str]:
        assert_read_only(list(engine_args))
        return [self.bash_binary, str(self.engine_path), "--no-color", *engine_args]

    async def run(
        self,
        engine_args: Sequence[str],
        *,
        timeout: float | None = None,
        operation: str = "unknown",
        context: str = "",
        namespace: str = "",
    ) -> RunResult:
        argv = self.build_argv(engine_args)
        timeout = min(timeout or settings.default_timeout_s, settings.max_timeout_s)
        started = time.monotonic()
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # The engine honours KUBECONFIG, so pointing it at the active
                # connection is what makes every report work in a container.
                env={**os.environ, **connections.active_environment()},
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if proc is not None:
                _terminate(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
            result = RunResult(
                argv=argv,
                exit_status=124,
                stdout="",
                stderr="",
                duration_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
                error=f"operation timed out after {timeout:.0f}s",
            )
            self._audit(result, operation, context, namespace, 0)
            return result
        except FileNotFoundError as exc:
            result = RunResult(
                argv=argv, exit_status=127, stdout="", stderr="", duration_ms=0,
                error=f"engine or bash not found: {exc}",
            )
            self._audit(result, operation, context, namespace, 0)
            return result
        except Exception as exc:  # pragma: no cover - defensive
            result = RunResult(
                argv=argv, exit_status=70, stdout="", stderr="",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=f"execution error: {exc}",
            )
            self._audit(result, operation, context, namespace, 0)
            return result

        truncated = False
        if len(stdout_b) > settings.max_output_bytes:
            stdout_b = stdout_b[: settings.max_output_bytes]
            truncated = True

        stdout = redact_text(stdout_b.decode("utf-8", "replace"))
        stderr = redact_text(stderr_b.decode("utf-8", "replace"))
        result = RunResult(
            argv=argv,
            exit_status=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=truncated,
        )
        self._audit(result, operation, context, namespace, _count_records(stdout))
        return result

    def _audit(
        self, result: RunResult, operation: str, context: str, namespace: str, records: int
    ) -> None:
        audit.add(
            AuditRecord(
                timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                operation=operation,
                context=context,
                namespace=namespace,
                duration_ms=result.duration_ms,
                exit_status=result.exit_status,
                record_count=records,
                source="LIVE",
            )
        )
