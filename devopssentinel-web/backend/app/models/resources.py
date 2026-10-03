"""Normalized domain resources derived from the engine's text reports.

The engine emits human-readable report lines. Rather than scrape ANSI, we
parse the *plain* (``--no-color``) report lines into a documented, typed
shape. Anything that cannot be parsed confidently is preserved in the raw
expert view instead of being guessed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["OK", "INFO", "NOTICE", "WARNING", "CRITICAL", "FAILED", "UNKNOWN", "PARTIAL"]
Confidence = Literal["CONFIRMED", "HIGH CONFIDENCE", "LIKELY", "POSSIBLE", "UNKNOWN"]


class Pod(BaseModel):
    name: str
    namespace: str = ""
    phase: str = "Unknown"
    ready: str = ""
    restarts: int = 0
    node: str = ""
    age: str = ""
    ip: str = ""
    owner: str = ""
    status: Severity = "UNKNOWN"
    containers: list[str] = Field(default_factory=list)


class Workload(BaseModel):
    name: str
    kind: str = "Deployment"
    namespace: str = ""
    ready: str = ""
    status: Severity = "UNKNOWN"
    restarts: int = 0
    node: str = ""
    age: str = ""
    cpu: str = ""
    memory: str = ""
    gitops: str = ""


class Event(BaseModel):
    time: str = ""
    severity: Severity = "INFO"
    reason: str = ""
    object: str = ""
    count: int = 1
    message: str = ""


class Finding(BaseModel):
    id: str
    severity: Severity = "UNKNOWN"
    lifecycle: str = "ACTIVE"
    domain: str = ""
    resource: str = ""
    finding: str = ""
    confidence: Confidence = "CONFIRMED"
    age: str = ""
    evidence: str = ""


class Certificate(BaseModel):
    name: str
    namespace: str = ""
    cn: str = ""
    issuer: str = ""
    expiry: str = ""
    days: int | None = None
    status: Severity = "UNKNOWN"
    consumers: int = 0
    gitops: str = ""


class GitOpsObject(BaseModel):
    name: str
    kind: str = "Kustomization"
    namespace: str = ""
    ready: bool | None = None
    suspended: bool = False
    revision: str = ""
    applied_revision: str = ""
    message: str = ""
    status: Severity = "UNKNOWN"


class Service(BaseModel):
    name: str
    namespace: str = ""
    type: str = "ClusterIP"
    cluster_ip: str = ""
    external_ip: str = ""
    ready_endpoints: int = 0
    not_ready_endpoints: int = 0
    selector: str = ""
    ports: str = ""
    status: Severity = "UNKNOWN"


class PVC(BaseModel):
    name: str
    namespace: str = ""
    status: str = "Bound"
    capacity: str = ""
    access_modes: str = ""
    storage_class: str = ""
    volume: str = ""
    severity: Severity = "OK"


class GraphNode(BaseModel):
    id: str
    kind: str
    name: str
    namespace: str = ""
    domain: str = "kubernetes"
    state: Severity = "UNKNOWN"
    confidence: Confidence = "CONFIRMED"


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str = "DEPENDS_ON"
    confidence: Confidence = "CONFIRMED"


class Graph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Capability(BaseModel):
    name: str
    status: str = "UNKNOWN"
    version: str = ""
    optional: bool = False


class LogLine(BaseModel):
    n: int
    text: str
    level: str = "INFO"


class LogBundle(BaseModel):
    pod: str
    container: str = ""
    previous: bool = False
    lines: list[LogLine] = Field(default_factory=list)
    patterns: list[dict[str, object]] = Field(default_factory=list)


class SearchResult(BaseModel):
    kind: str
    name: str
    namespace: str = ""
    route: str = ""
    state: Severity = "UNKNOWN"
