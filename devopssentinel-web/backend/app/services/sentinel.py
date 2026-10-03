"""DevOpsSentinel adapter: the ONLY place that knows how to invoke the engine.

The browser never supplies a command. It supplies an *operation id* plus
validated scope (context, namespace, resource name). This module maps that
to an allowlisted argv and returns the engine's own ``--json`` object.

No ANSI scraping: we always request ``--json`` (the engine's stable
machine-readable mode) and parse the resulting object.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from ..models import EngineLineEnvelope, OperationInfo
from ..security import validate_context, validate_incident_id, validate_kind, validate_name
from .runner import RunResult, Runner


@dataclass(frozen=True)
class OperationSpec:
    id: str
    title: str
    domain: str
    mode: str
    timeout_s: float = 45.0
    requires: tuple[str, ...] = ()
    extra_args: Callable[[dict], list[str]] = lambda p: []

    def build_args(self, context: str, namespace: str, params: dict) -> list[str]:
        args: list[str] = []
        if context:
            args += ["--context", validate_context(context)]
        if namespace:
            args += ["--namespace", validate_name(namespace, field="namespace")]
        args += ["--" + self.mode]
        args += self.extra_args(params)
        # Always request the engine's stable machine-readable mode; the adapter
        # never parses ANSI terminal output.
        args += ["--json"]
        return args


def _dep_args(params: dict) -> list[str]:
    kind = validate_kind(str(params.get("kind", "Deployment")))
    name = validate_name(str(params.get("name", "")))
    return [f"{kind}/{name}"]


def _triage_workload_args(params: dict) -> list[str]:
    kind = validate_kind(str(params.get("kind", "Deployment")))
    name = validate_name(str(params.get("name", "")))
    return [f"{kind}/{name}"]


def _evidence_args(params: dict) -> list[str]:
    return [validate_incident_id(str(params.get("id", "INCIDENT")))]


OPERATIONS: dict[str, OperationSpec] = {
    "system.health": OperationSpec("system.health", "Health", "system", "health", 30),
    "system.capabilities": OperationSpec(
        "system.capabilities", "Capabilities", "system", "capabilities", 20
    ),
    "system.doctor": OperationSpec("system.doctor", "Doctor", "system", "doctor", 30),
    "system.snapshot": OperationSpec(
        "system.snapshot", "Operations Snapshot", "system", "snapshot", 60
    ),
    "system.live_validate": OperationSpec(
        "system.live_validate", "Live Validation", "system", "live-validate", 60
    ),
    "system.self_test": OperationSpec("system.self_test", "Self Test", "system", "self-test", 60),
    "workloads.resources": OperationSpec(
        "workloads.resources", "Resources", "workloads", "resources", 45
    ),
    "workloads.triage": OperationSpec("workloads.triage", "Triage", "workloads", "triage", 60),
    "workloads.triage_workload": OperationSpec(
        "workloads.triage_workload",
        "Workload Triage",
        "workloads",
        "triage-workload",
        60,
        extra_args=_triage_workload_args,
    ),
    "graph.dependency": OperationSpec(
        "graph.dependency", "Dependency", "topology", "dependency", 60, extra_args=_dep_args
    ),
    "graph.gitops": OperationSpec("graph.gitops", "GitOps Graph", "topology", "gitops-graph", 60),
    "gitops.overview": OperationSpec("gitops.overview", "GitOps", "gitops", "gitops", 45),
    "pki.certificates": OperationSpec("pki.certificates", "Certificates", "pki", "certificates", 60),
    "pki.cert_expiry": OperationSpec(
        "pki.cert_expiry", "Certificate Expiry", "pki", "cert-expiry", 60
    ),
    "network.topology": OperationSpec("network.topology", "Network", "network", "network", 45),
    "storage.dependencies": OperationSpec(
        "storage.dependencies", "Storage", "storage", "storage", 45
    ),
    "etdp.platform": OperationSpec("etdp.platform", "ETDP Platform", "etdp", "etdp", 60),
    "database.postgres": OperationSpec(
        "database.postgres", "PostgreSQL / Generic DB", "database", "postgres-discovery", 60
    ),
    "kafka.discovery": OperationSpec("kafka.discovery", "Kafka", "kafka", "kafka-discovery", 60),
    "evidence.create": OperationSpec(
        "evidence.create", "Evidence", "operations", "evidence", 120, extra_args=_evidence_args
    ),
}


class SentinelError(RuntimeError):
    pass


class SentinelAdapter:
    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or Runner()

    def operations(self) -> list[OperationInfo]:
        return [
            OperationInfo(
                id=spec.id,
                title=spec.title,
                domain=spec.domain,
                mode=spec.mode,
                requires=list(spec.requires),
                timeoutS=spec.timeout_s,
            )
            for spec in OPERATIONS.values()
        ]

    def spec(self, operation_id: str) -> OperationSpec:
        spec = OPERATIONS.get(operation_id)
        if spec is None:
            raise SentinelError(f"unknown operation: {operation_id}")
        return spec

    async def invoke(
        self,
        operation_id: str,
        *,
        context: str = "",
        namespace: str = "",
        params: dict | None = None,
    ) -> tuple[RunResult, EngineLineEnvelope | None]:
        spec = self.spec(operation_id)
        params = params or {}
        args = spec.build_args(context, namespace, params)
        result = await self.runner.run(
            args,
            timeout=spec.timeout_s,
            operation=operation_id,
            context=context,
            namespace=namespace,
        )
        envelope = self.parse_json(result.stdout)
        return result, envelope

    @staticmethod
    def parse_json(stdout: str) -> EngineLineEnvelope | None:
        text = stdout.strip()
        if not text:
            return None
        candidate = text
        if not candidate.startswith("{"):
            start = candidate.find("{")
            if start < 0:
                return None
            candidate = candidate[start:]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or "lines" not in payload:
            return None
        return EngineLineEnvelope.model_validate(payload)


adapter = SentinelAdapter()

