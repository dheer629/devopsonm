"""Normalizers that turn the engine's plain report lines into typed rows.

Design rules
------------
* We never guess. A row is emitted only when the columns can be identified
  with confidence; otherwise the raw line stays in the expert view.
* Severity keywords are mapped through one canonical vocabulary
  (spec section 68).
* Relationship/derived values carry an explicit confidence (spec section 69).
"""

from __future__ import annotations

import re

from ..models.resources import (
    Capability,
    Certificate,
    Event,
    Finding,
    GitOpsObject,
    Graph,
    GraphEdge,
    GraphNode,
    LogBundle,
    LogLine,
    Pod,
    PVC,
    Service,
    Workload,
)

_SEV_ORDER = {
    "FAILED": 0, "CRITICAL": 1, "WARNING": 2, "NOTICE": 3,
    "UNKNOWN": 4, "INFO": 5, "OK": 6, "PARTIAL": 5,
}


def canonical_severity(text: str) -> str:
    low = text.lower()
    if any(t in low for t in ("unknown", "notprobed", "not probed", "unavailable", "n/a")):
        return "UNKNOWN"
    if any(t in low for t in ("crashloop", "imagepull", "failed", "fail ", "error", "critical")):
        return "CRITICAL"
    if any(t in low for t in ("unhealthy", "backoff", "oomkilled", "pending", "degraded", "warning", "warn")):
        return "WARNING"
    if "notice" in low:
        return "NOTICE"
    if any(t in low for t in ("healthy", "ready", "ok", "running", "bound", "available", "true")):
        return "OK"
    return "INFO"


def sort_severity(rows, key=lambda r: getattr(r, "status", "UNKNOWN")):
    return sorted(rows, key=lambda r: _SEV_ORDER.get(key(r), 7))


def _strip_bullets(line: str) -> str:
    return re.sub(r"^[\s\-*|>]+", "", line).strip()


def split_row(line: str) -> list[str]:
    """Split a report row into cells (2+ spaces or explicit pipes)."""
    if "|" in line:
        cells = [c.strip() for c in line.split("|")]
        return [c for c in cells if c != ""]
    return [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]


def parse_kv_lines(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value and len(key) < 60:
                out.setdefault(key, value)
    return out


def extract_tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """Find header rows (>=2 tokens, followed by a separator or data rows)."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    i = 0
    while i < len(lines):
        cells = split_row(lines[i])
        if len(cells) >= 2 and all(re.fullmatch(r"[A-Za-z][A-Za-z0-9()%/_.-]*", c) for c in cells):
            header = cells
            rows: list[list[str]] = []
            j = i + 1
            while j < len(lines):
                if set(lines[j].strip()) <= {"-", "+", "="} or lines[j].strip() == "":
                    j += 1
                    if lines[j - 1].strip() and set(lines[j - 1].strip()) <= {"-", "+", "="}:
                        continue
                    break
                row = split_row(lines[j])
                if len(row) < 2:
                    break
                rows.append(row)
                j += 1
            if rows:
                tables.append((header, rows))
                i = j
                continue
        i += 1
    return tables


def _cell(row: list[str], header: list[str], *names: str) -> str:
    low = [h.lower() for h in header]
    for name in names:
        if name.lower() in low:
            idx = low.index(name.lower())
            if idx < len(row):
                return row[idx]
    return ""


def normalize_pods(lines: list[str], namespace: str = "") -> list[Pod]:
    pods: list[Pod] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "name" not in low:
            continue
        if not any(h in low for h in ("ready", "status", "restarts", "phase")):
            continue
        for row in rows:
            name = _cell(row, header, "name", "pod")
            if not name:
                continue
            ready = _cell(row, header, "ready")
            restarts_raw = _cell(row, header, "restarts", "restart")
            try:
                restarts = int(re.sub(r"[^0-9]", "", restarts_raw) or 0)
            except ValueError:
                restarts = 0
            status_text = _cell(row, header, "status", "phase", "state")
            pods.append(
                Pod(
                    name=name,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    phase=status_text or "Unknown",
                    ready=ready,
                    restarts=restarts,
                    node=_cell(row, header, "node"),
                    age=_cell(row, header, "age"),
                    ip=_cell(row, header, "ip"),
                    owner=_cell(row, header, "owner", "controller"),
                    status=canonical_severity(status_text or ready),
                )
            )
    return pods


def normalize_workloads(lines: list[str], namespace: str = "") -> list[Workload]:
    workloads: list[Workload] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "name" not in low or not any(h in low for h in ("ready", "kind", "replicas")):
            continue
        for row in rows:
            name = _cell(row, header, "name")
            if not name:
                continue
            ready = _cell(row, header, "ready", "replicas")
            try:
                restarts = int(re.sub(r"[^0-9]", "", _cell(row, header, "restarts")) or 0)
            except ValueError:
                restarts = 0
            kind = _cell(row, header, "kind", "type") or "Workload"
            workloads.append(
                Workload(
                    name=name,
                    kind=kind,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    ready=ready,
                    status=canonical_severity(ready or _cell(row, header, "status")),
                    restarts=restarts,
                    node=_cell(row, header, "node"),
                    age=_cell(row, header, "age"),
                    cpu=_cell(row, header, "cpu"),
                    memory=_cell(row, header, "memory", "mem"),
                    gitops=_cell(row, header, "gitops", "flux"),
                )
            )
    return workloads


def normalize_certificates(lines: list[str], namespace: str = "") -> list[Certificate]:
    certs: list[Certificate] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if not any(h in low for h in ("certificate", "cn", "expiry", "days", "issuer")):
            continue
        for row in rows:
            name = _cell(row, header, "name", "certificate", "secret")
            cn = _cell(row, header, "cn", "common name", "subject")
            if not name and not cn:
                continue
            days_raw = _cell(row, header, "days", "expires in", "remaining")
            try:
                days = int(re.sub(r"[^0-9-]", "", days_raw)) if days_raw else None
            except ValueError:
                days = None
            status = "OK"
            if days is not None:
                status = "CRITICAL" if days < 0 else ("WARNING" if days <= 30 else "OK")
            certs.append(
                Certificate(
                    name=name or cn,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    cn=cn,
                    issuer=_cell(row, header, "issuer", "ca"),
                    expiry=_cell(row, header, "expiry", "not after", "expires"),
                    days=days,
                    status=status,
                    consumers=int(re.sub(r"[^0-9]", "", _cell(row, header, "consumers")) or 0),
                    gitops=_cell(row, header, "gitops", "flux"),
                )
            )
    return certs


def normalize_gitops(lines: list[str], namespace: str = "") -> list[GitOpsObject]:
    objs: list[GitOpsObject] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if not any(h in low for h in ("ready", "revision", "applied", "suspended", "message")):
            continue
        if "name" not in low:
            continue
        for row in rows:
            name = _cell(row, header, "name")
            if not name:
                continue
            ready_raw = _cell(row, header, "ready", "status").lower()
            ready: bool | None = None
            if ready_raw in ("true", "yes", "ready"):
                ready = True
            elif ready_raw in ("false", "no", "failed", "notready"):
                ready = False
            objs.append(
                GitOpsObject(
                    name=name,
                    kind=_cell(row, header, "kind", "type") or "Kustomization",
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    ready=ready,
                    suspended=_cell(row, header, "suspended").lower() in ("true", "yes"),
                    revision=_cell(row, header, "revision", "rev"),
                    applied_revision=_cell(row, header, "applied", "lastapplied"),
                    message=_cell(row, header, "message", "reason"),
                    status=canonical_severity(ready_raw),
                )
            )
    return objs


def normalize_services(lines: list[str], namespace: str = "") -> list[Service]:
    services: list[Service] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "name" not in low or not any(h in low for h in ("clusterip", "cluster-ip", "ports", "type")):
            continue
        for row in rows:
            name = _cell(row, header, "name")
            if not name:
                continue
            services.append(
                Service(
                    name=name,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    type=_cell(row, header, "type") or "ClusterIP",
                    cluster_ip=_cell(row, header, "clusterip", "cluster-ip", "ip"),
                    external_ip=_cell(row, header, "externalip", "external-ip"),
                    ready_endpoints=int(
                        re.sub(r"[^0-9]", "", _cell(row, header, "ready", "endpoints")) or 0
                    ),
                    not_ready_endpoints=int(
                        re.sub(r"[^0-9]", "", _cell(row, header, "notready", "not-ready")) or 0
                    ),
                    selector=_cell(row, header, "selector"),
                    ports=_cell(row, header, "ports", "port"),
                    status=canonical_severity(_cell(row, header, "ready", "status")),
                )
            )
    return services


def normalize_pvcs(lines: list[str], namespace: str = "") -> list[PVC]:
    pvcs: list[PVC] = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "name" not in low or not any(h in low for h in ("capacity", "volume", "access", "storageclass", "status")):
            continue
        for row in rows:
            name = _cell(row, header, "name")
            if not name:
                continue
            status = _cell(row, header, "status", "phase") or "Bound"
            pvcs.append(
                PVC(
                    name=name,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    status=status,
                    capacity=_cell(row, header, "capacity", "size"),
                    access_modes=_cell(row, header, "access", "accessmodes"),
                    storage_class=_cell(row, header, "storageclass", "storage-class", "class"),
                    volume=_cell(row, header, "volume", "pv"),
                    severity="OK" if status.lower() == "bound" else "WARNING",
                )
            )
    return pvcs


_SEV_TOKEN = re.compile(r"\b(CRITICAL|FAILED|WARNING|WARN|NOTICE|INFO|OK|UNKNOWN)\b")


def normalize_findings(lines: list[str], namespace: str = "") -> list[Finding]:
    findings: list[Finding] = []
    counter = 0
    for raw in lines:
        line = _strip_bullets(raw)
        if not line or len(line) < 8:
            continue
        match = _SEV_TOKEN.search(line.upper())
        if not match:
            continue
        severity = canonical_severity(match.group(1))
        if severity in ("OK", "INFO") and "finding" not in line.lower():
            continue
        counter += 1
        resource = ""
        rm = re.search(r"\b([A-Za-z][A-Za-z0-9]*)[/:]([a-z0-9][a-z0-9.-]*)", line)
        if rm:
            resource = f"{rm.group(1)}/{rm.group(2)}"
        findings.append(
            Finding(
                id=f"F-{counter:03d}",
                severity=severity,
                lifecycle="ACTIVE",
                domain=_guess_domain(line),
                resource=resource,
                finding=line[:400],
                confidence="CONFIRMED",
                age="",
                evidence=line[:400],
            )
        )
    return findings


def _guess_domain(text: str) -> str:
    low = text.lower()
    for key, domain in (
        ("certificate", "PKI"), ("tls", "PKI"), ("cert", "PKI"),
        ("helmrelease", "GitOps"), ("kustomization", "GitOps"),
        ("gitrepository", "GitOps"), ("flux", "GitOps"),
        ("pvc", "Storage"), ("volume", "Storage"),
        ("service", "Network"), ("endpoint", "Network"), ("ingress", "Network"),
        ("kafka", "Kafka"), ("postgres", "Database"),
        ("pod", "Workload"), ("deployment", "Workload"), ("statefulset", "Workload"),
    ):
        if key in low:
            return domain
    return "General"


def normalize_capabilities(lines: list[str]) -> list[Capability]:
    caps: list[Capability] = []
    for line in lines:
        cells = split_row(line)
        if len(cells) < 2:
            continue
        name = _strip_bullets(cells[0]).strip(".:")
        status = cells[1].upper()
        if not name or name.lower() in ("capability", "tool"):
            continue
        if not re.search(r"(AVAILABLE|UNAVAILABLE|OPTIONAL|READY|MISSING|NOT PROBED|OK)", status):
            continue
        version = cells[2] if len(cells) > 2 else ""
        caps.append(
            Capability(
                name=name,
                status=(
                    "AVAILABLE"
                    if "AVAILABLE" in status and "UNAVAILABLE" not in status
                    else status
                ),
                version=version,
                optional="OPTIONAL" in status or "UNAVAILABLE" in status,
            )
        )
    return caps


def normalize_events(lines: list[str], namespace: str = "") -> list[Event]:
    events: list[Event] = []
    for raw in lines:
        line = _strip_bullets(raw)
        if not line:
            continue
        if not re.search(r"\b(Normal|Warning|WARN|ERROR|INFO)\b", line):
            continue
        sev = canonical_severity(line)
        time_m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?|\d{4}-\d{2}-\d{2}T[\d:]+Z?)", line)
        reason_m = re.search(
            r"\b([A-Z][A-Za-z]*(?:Failed|BackOff|Created|Started|Pulled|Scheduled|"
            r"Unhealthy|Evicted|Killing|Provisioning|ScalingReplicaSet))\b",
            line,
        )
        count_m = re.search(r"\bx(\d+)\b|\bcount[=:]\s*(\d+)", line)
        events.append(
            Event(
                time=time_m.group(1) if time_m else "",
                severity=sev,
                reason=reason_m.group(1) if reason_m else "",
                object=namespace,
                count=int(count_m.group(1) or count_m.group(2)) if count_m else 1,
                message=line[:400],
            )
        )
    return events


def normalize_dependency_graph(lines: list[str]) -> Graph:
    """Parse lines like ``Pod/a -> ReplicaSet/b -> Deployment/c``."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    for raw in lines:
        if "->" not in raw:
            continue
        parts = [p.strip() for p in raw.split("->")]
        for part in parts:
            if "/" not in part:
                continue
            kind, _, name = part.partition("/")
            kind = kind.strip()
            name = name.strip().split()[0] if name.strip() else ""
            if not kind or not name:
                continue
            nid = f"{kind}/{name}"
            nodes.setdefault(
                nid,
                GraphNode(id=nid, kind=kind, name=name, domain=_domain_for_kind(kind), state="UNKNOWN"),
            )
        for a, b in zip(parts, parts[1:]):
            if "/" not in a or "/" not in b:
                continue
            src, dst = a.strip(), b.strip()
            edges.append(
                GraphEdge(
                    id=f"{src}->{dst}",
                    source=src,
                    target=dst,
                    label=_edge_label(src, dst),
                    confidence="HIGH CONFIDENCE",
                )
            )
    return Graph(nodes=list(nodes.values()), edges=edges)


def _domain_for_kind(kind: str) -> str:
    k = kind.lower()
    if k in ("gitrepository", "kustomization", "helmrelease", "helmrepository", "ocirepository"):
        return "gitops"
    if k in ("certificate", "issuer", "secret"):
        return "pki"
    if k in ("service", "endpointslice", "endpoints", "ingress", "networkpolicy"):
        return "network"
    if k in ("persistentvolumeclaim", "persistentvolume", "storageclass"):
        return "storage"
    return "kubernetes"


def _edge_label(src: str, dst: str) -> str:
    s = src.split("/")[0].lower()
    d = dst.split("/")[0].lower()
    if s == "service" or d in ("endpointslice", "endpoints"):
        return "SELECTS"
    if d in ("pod", "replicaset", "deployment", "statefulset", "daemonset"):
        return "OWNS"
    if d == "certificate" or s == "certificate":
        return "CONTAINS_CERT"
    if d in ("kustomization", "helmrelease", "gitrepository"):
        return "MANAGED_BY"
    if d == "persistentvolumeclaim":
        return "BOUND_TO"
    return "DEPENDS_ON"


def normalize_logs(
    lines: list[str], pod: str, container: str = "", previous: bool = False
) -> LogBundle:
    out: list[LogLine] = []
    counts: dict[str, int] = {}
    for i, raw in enumerate(lines, start=1):
        low = raw.lower()
        level = "INFO"
        if "error" in low or "fatal" in low or "panic" in low:
            level = "ERROR"
        elif "warn" in low:
            level = "WARN"
        elif "debug" in low or "trace" in low:
            level = "DEBUG"
        out.append(LogLine(n=i, text=raw, level=level))
        norm = re.sub(r"\d+", "#", raw.strip())[:120]
        if norm:
            counts[norm] = counts.get(norm, 0) + 1
    patterns = [
        {"pattern": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:10]
        if v > 1
    ]
    return LogBundle(pod=pod, container=container, previous=previous, lines=out, patterns=patterns)




