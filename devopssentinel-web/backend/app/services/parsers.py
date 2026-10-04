"""Normalizers that turn the engine's plain report lines into typed rows.

Aligned with the real output of DevOpsSentinel v4.2.2 (verified against a live
vcluster: `--resources`, `--gitops`, `--certificates`, `--network`, `--triage`,
`--doctor`).

Design rules
------------
* The engine emits TAB-separated tables and `Kind/name [STATUS REASON]` blocks.
  We never guess: a row is emitted only when the columns are identifiable.
* Severity keywords map through one canonical vocabulary.
* Derived values (e.g. workloads aggregated from pod owners) carry evidence.
"""

from __future__ import annotations

import re

from ..models.resources import (
    Capability,
    Certificate,
    DbService,
    Event,
    Finding,
    GitOpsObject,
    Graph,
    GraphEdge,
    GraphNode,
    KafkaService,
    LogBundle,
    LogLine,
    Pod,
    PVC,
    Service,
    Workload,
)

_SEV_ORDER = {
    "FAILED": 0, "CRITICAL": 1, "WARNING": 2, "NOTICE": 3,
    "UNKNOWN": 4, "INFO": 5, "PARTIAL": 5, "OK": 6,
}

_ENGINE_SEVERITY = {
    "FAIL": "FAILED",
    "ERROR": "CRITICAL",
    "CRIT": "CRITICAL",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "NOTICE": "NOTICE",
    "INFO": "INFO",
    "OK": "OK",
    "UNKNOWN": "UNKNOWN",
    "PENDING": "WARNING",
    "SUSPENDED": "NOTICE",
}

_POD_CRITICAL = (
    "crashloopbackoff", "imagepullbackoff", "errimagepull", "oomkilled",
    "evicted", "failed", "nodeaffinity", "unschedulable",
    "createcontainerconfigerror", "invalidimagename",
)
_POD_WARNING = ("pending", "notready", "containercreating", "podinitializing", "unknown")


def canonical_severity(text: str) -> str:
    low = (text or "").lower()
    if any(t in low for t in ("notprobed", "not probed", "unavailable", "n/a", "unknown", "none")):
        return "UNKNOWN"
    if any(t in low for t in _POD_CRITICAL):
        return "CRITICAL"
    if any(t in low for t in _POD_WARNING):
        return "WARNING"
    if "warn" in low:
        return "WARNING"
    if "notice" in low or "suspend" in low:
        return "NOTICE"
    if any(
        t in low
        for t in ("running", "healthy", "ready", "ok", "bound", "active", "available", "true")
    ):
        return "OK"
    return "INFO"


def engine_severity(token: str) -> str:
    """Map an engine severity token (FAIL/WARN/OK/...) to canonical form."""
    return _ENGINE_SEVERITY.get((token or "").strip().upper(), canonical_severity(token))


def pod_severity(phase: str, ready: str) -> str:
    """Derive pod status from phase + ready fraction.

    Readiness is the authoritative signal here. Restart counts are shown as a
    separate column and are reported as findings by the engine's own triage,
    so this function deliberately does not invent a restart threshold.
    """
    low = (phase or "").lower()
    for token in _POD_CRITICAL:
        if token in low:
            return "CRITICAL"
    if "/" in ready:
        have, _, want = ready.partition("/")
        try:
            if int(have) == 0:
                return "CRITICAL"
            if int(have) < int(want):
                return "WARNING"
        except ValueError:
            pass
    if any(t in low for t in _POD_WARNING):
        return "WARNING"
    if "running" in low or low in ("succeeded", "completed"):
        return "OK"
    return "UNKNOWN"


def sort_severity(rows, key=lambda r: getattr(r, "status", "UNKNOWN")):
    return sorted(rows, key=lambda r: _SEV_ORDER.get(key(r), 7))


# --------------------------------------------------------------------------
# Row / table primitives
# --------------------------------------------------------------------------

_HEADER_CELL = re.compile(r"^[A-Z][A-Z0-9 ()%/_.+-]*$")


def split_row(line: str) -> list[str]:
    """Split a report row. The engine uses TABs; also tolerate pipes/columns."""
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    if "|" in line:
        return [c.strip() for c in line.split("|")]
    return [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]


def _is_header_row(cells: list[str]) -> bool:
    """A header row is 2+ all-caps column names (e.g. POD, READY, CPU USED)."""
    if len(cells) < 2:
        return False
    return all(_HEADER_CELL.match(c) for c in cells)


def extract_tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """Find header rows and the data rows that follow them."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index < len(lines):
        cells = split_row(lines[index])
        if _is_header_row(cells):
            header = cells
            rows: list[list[str]] = []
            cursor = index + 1
            while cursor < len(lines):
                line = lines[cursor]
                if not line.strip():
                    break
                row = split_row(line)
                if len(row) < 2 or _is_header_row(row):
                    break
                rows.append(row)
                cursor += 1
            if rows:
                tables.append((header, rows))
                index = cursor
                continue
        index += 1
    return tables


def _cell(row: list[str], header: list[str], *names: str) -> str:
    low = [h.lower() for h in header]
    for name in names:
        target = name.lower()
        if target in low:
            idx = low.index(target)
            if idx < len(row):
                return row[idx].strip()
    return ""


def parse_kv_lines(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if key and value and len(key) < 60:
                out.setdefault(key, value)
    return out


# --------------------------------------------------------------------------
# Pods (engine `--resources` POD table)
# --------------------------------------------------------------------------

def _pod_tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """Tables that look like the engine's POD inventory."""
    out = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if ("pod" in low or "name" in low) and any(
            h in low for h in ("ready", "status", "restarts", "phase")
        ):
            out.append((header, rows))
    return out


def normalize_pods(lines: list[str], namespace: str = "") -> list[Pod]:
    pods: list[Pod] = []
    for header, rows in _pod_tables(lines):
        for row in rows:
            name = _cell(row, header, "pod", "name")
            if not name or name.upper() == "TOTALS":
                continue
            ready = _cell(row, header, "ready")
            restarts_raw = _cell(row, header, "restarts", "restart")
            try:
                restarts = int(re.sub(r"[^0-9]", "", restarts_raw) or 0)
            except ValueError:
                restarts = 0
            phase = _cell(row, header, "status", "phase", "state") or "Unknown"
            containers = _cell(row, header, "containers")
            pods.append(
                Pod(
                    name=name,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    phase=phase,
                    ready=ready,
                    restarts=restarts,
                    node=_cell(row, header, "node"),
                    age=_cell(row, header, "age"),
                    ip=_cell(row, header, "ip"),
                    owner=_cell(row, header, "owner", "controller"),
                    status=pod_severity(phase, ready),
                    containers=[c for c in containers.split() if c],
                )
            )
    return pods


def pod_resource_usage(lines: list[str]) -> dict[str, dict[str, str]]:
    """Map pod name -> {'cpu': ..., 'memory': ...} from the POD table."""
    usage: dict[str, dict[str, str]] = {}
    for header, rows in _pod_tables(lines):
        for row in rows:
            name = _cell(row, header, "pod", "name")
            if not name or name.upper() == "TOTALS":
                continue
            usage[name] = {
                "cpu": _cell(row, header, "cpu used", "cpu"),
                "memory": _cell(row, header, "mem used", "memory", "mem"),
            }
    return usage


def normalize_workloads(lines: list[str], namespace: str = "") -> list[Workload]:
    """Derive workloads from the pod inventory via pod owner references.

    The engine's `--resources` report lists pods (with an OWNER column) and
    totals; there is no separate workload table. Aggregating by owner is an
    evidence-based projection of that same data.
    """
    pods = normalize_pods(lines, namespace)
    usage = pod_resource_usage(lines)
    groups: dict[str, list[Pod]] = {}
    for pod in pods:
        groups.setdefault(pod.owner or "Unknown", []).append(pod)

    workloads: list[Workload] = []
    for owner, members in groups.items():
        kind, _, name = owner.partition("/")
        if not name:
            kind, name = "Pod", owner
        ready_count = sum(1 for p in members if p.status == "OK")
        worst = min(
            (p.status for p in members),
            key=lambda s: _SEV_ORDER.get(s, 7),
            default="UNKNOWN",
        )
        cpu = next((usage[p.name]["cpu"] for p in members if usage.get(p.name, {}).get("cpu")), "")
        memory = next(
            (usage[p.name]["memory"] for p in members if usage.get(p.name, {}).get("memory")), ""
        )
        workloads.append(
            Workload(
                name=name,
                kind=kind if kind != "Unknown" else "Pod",
                namespace=namespace,
                ready=f"{ready_count}/{len(members)}",
                status=worst,
                restarts=max((p.restarts for p in members), default=0),
                node=members[0].node if members else "",
                age=members[0].age if members else "",
                cpu=cpu,
                memory=memory,
                gitops="",
            )
        )
    return sort_severity(workloads)


# --------------------------------------------------------------------------
# Findings + events (engine `--triage` SEVERITY table)
# --------------------------------------------------------------------------

_CATEGORY_DOMAIN = {
    "PODS": "Workload",
    "RESTARTS": "Workload",
    "CONTAINERS": "Workload",
    "EVENTS": "Workload",
    "WORKLOADS": "Workload",
    "GITOPS": "GitOps",
    "FLUX": "GitOps",
    "CERTIFICATES": "PKI",
    "TLS": "PKI",
    "SERVICES": "Network",
    "ENDPOINTS": "Network",
    "INGRESS": "Network",
    "NETWORK": "Network",
    "STORAGE": "Storage",
    "PVC": "Storage",
    "KAFKA": "Kafka",
    "POSTGRES": "Database",
    "DATABASE": "Database",
    "ETDP": "ETDP",
}

_SEV_TOKEN = re.compile(r"\b(FAIL|FAILED|CRITICAL|WARN|WARNING|NOTICE|INFO|OK|UNKNOWN)\b")


def _triage_tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    out = []
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "severity" in low and "resource" in low:
            out.append((header, rows))
    return out


def normalize_findings(lines: list[str], namespace: str = "") -> list[Finding]:
    findings: list[Finding] = []
    counter = 0

    for header, rows in _triage_tables(lines):
        for row in rows:
            severity = engine_severity(_cell(row, header, "severity"))
            resource = _cell(row, header, "resource")
            issue = _cell(row, header, "issue")
            evidence = _cell(row, header, "evidence")
            category = _cell(row, header, "category").upper()
            if not issue:
                continue
            counter += 1
            findings.append(
                Finding(
                    id=f"F-{counter:03d}",
                    severity=severity,
                    lifecycle="ACTIVE",
                    domain=_CATEGORY_DOMAIN.get(category, "General"),
                    resource=resource,
                    finding=issue[:400],
                    confidence="CONFIRMED",
                    age="",
                    evidence=evidence[:400],
                )
            )

    if findings:
        return findings

    # Fallback for report modes that embed severity-prefixed lines.
    for raw in lines:
        line = re.sub(r"^[\s\-*|>]+", "", raw).strip()
        if len(line) < 8:
            continue
        match = _SEV_TOKEN.search(line.upper())
        if not match:
            continue
        severity = engine_severity(match.group(1))
        if severity in ("OK", "INFO") and "finding" not in line.lower():
            continue
        counter += 1
        resource = ""
        rm = re.search(r"\b([A-Za-z][A-Za-z0-9]*)/([a-z0-9][a-z0-9.-]*)", line)
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


def normalize_events(lines: list[str], namespace: str = "") -> list[Event]:
    events: list[Event] = []
    for header, rows in _triage_tables(lines):
        for row in rows:
            if _cell(row, header, "category").upper() != "EVENTS":
                continue
            issue = _cell(row, header, "issue")
            evidence = _cell(row, header, "evidence")
            reason, _, message = issue.partition(":")
            time_match = re.search(r"latest=(\S+)", evidence)
            count_match = re.search(r"count=(\d+)", evidence)
            events.append(
                Event(
                    time=time_match.group(1) if time_match else "",
                    severity=engine_severity(_cell(row, header, "severity")),
                    reason=reason.strip(),
                    object=_cell(row, header, "resource") or namespace,
                    count=int(count_match.group(1)) if count_match else 1,
                    message=(message.strip() or issue)[:400],
                )
            )
    return events


# --------------------------------------------------------------------------
# Capabilities (engine `--doctor` tooling section)
# --------------------------------------------------------------------------

_CAP_STATUS = re.compile(
    r"^(AVAILABLE|UNAVAILABLE|NOT INSTALLED|OPTIONAL/UNAVAILABLE|OPTIONAL|OK|READY|MISSING|NOT PROBED)$"
)


def normalize_capabilities(lines: list[str]) -> list[Capability]:
    caps: list[Capability] = []
    for line in lines:
        cells = split_row(line)
        if len(cells) < 2:
            continue
        name = cells[0].strip().strip(".:")
        status = cells[1].strip().upper()
        if not name or "[" in name or ":" in name or len(name) > 40:
            continue
        if not _CAP_STATUS.match(status):
            continue
        caps.append(
            Capability(
                name=name,
                status=status,
                version=cells[2].strip() if len(cells) > 2 else "",
                optional=status.startswith("OPTIONAL") or status in ("UNAVAILABLE", "NOT INSTALLED"),
            )
        )
    return caps


# --------------------------------------------------------------------------
# GitOps (engine `--gitops` block format)
# --------------------------------------------------------------------------

_BLOCK_HEAD = re.compile(r"^([A-Za-z][A-Za-z0-9]*)/(\S+)\s+\[([A-Z]+)(?:\s+([A-Z_]+))?\]")
_KV = re.compile(r"([A-Za-z][A-Za-z0-9/_.-]*)=(\S+)")


def normalize_gitops(lines: list[str], namespace: str = "") -> list[GitOpsObject]:
    """Parse the engine's Flux block format:

        GitRepository/name [FAIL RECONCILIATION_FAILED]
          Ready=False suspend=false generation=1 observed=1
          Artifact=main@sha1:... applied=- attempted=-
          Reason=GitOperationFailed message=...
    """
    objects: list[GitOpsObject] = []
    current: dict[str, object] | None = None

    def flush() -> None:
        if current is None:
            return
        kv: dict[str, str] = current["kv"]  # type: ignore[assignment]
        ready_raw = kv.get("Ready", "").lower()
        ready: bool | None = None
        if ready_raw == "true":
            ready = True
        elif ready_raw == "false":
            ready = False
        revision = kv.get("Artifact", "")
        if revision in ("", "-"):
            revision = kv.get("Source", "")
        objects.append(
            GitOpsObject(
                name=str(current["name"]),
                kind=str(current["kind"]),
                namespace=namespace,
                ready=ready,
                suspended=kv.get("suspend", "").lower() == "true",
                revision=revision,
                applied_revision=kv.get("applied", "") if kv.get("applied") != "-" else "",
                message=kv.get("message", ""),
                status=engine_severity(str(current["severity"])),
            )
        )

    for line in lines:
        head = _BLOCK_HEAD.match(line)
        if head:
            flush()
            current = {
                "kind": head.group(1),
                "name": head.group(2),
                "severity": head.group(3),
                "reason": head.group(4) or "",
                "kv": {},
            }
            continue
        if current is None:
            continue
        if not line.startswith((" ", "\t")):
            continue
        kv: dict[str, str] = current["kv"]  # type: ignore[assignment]
        # `message=` values contain spaces, so capture them to end-of-line
        # before the generic key=value sweep.
        message = re.search(r"\bmessage=(.*)$", line)
        if message:
            kv.setdefault("message", message.group(1).strip())
        remainder = re.sub(r"\bmessage=.*$", "", line)
        for key, value in _KV.findall(remainder):
            kv.setdefault(key, value)

    flush()
    return objects


# --------------------------------------------------------------------------
# Network (engine `--network` Service/EndpointSlice tree)
# --------------------------------------------------------------------------

_SVC_LINE = re.compile(
    r"^Service/(\S+)\s+type=(\S+)(?:\s+clusterIP=(\S+))?(?:\s+externalIP=(\S+))?(?:\s+ports=(.*))?$"
)
_EPS_LINE = re.compile(r"EndpointSlice:\s*(\S+)\s+ready=(\d+)/(\d+)")


def normalize_services(lines: list[str], namespace: str = "") -> list[Service]:
    services: list[Service] = []

    for line in lines:
        match = _SVC_LINE.match(line.strip())
        if match:
            name, svc_type, cluster_ip, external_ip, ports = match.groups()
            services.append(
                Service(
                    name=name,
                    namespace=namespace,
                    type=svc_type,
                    cluster_ip=cluster_ip or "",
                    external_ip=external_ip or "",
                    ports=(ports or "").strip(),
                    status="UNKNOWN",
                )
            )
            continue
        eps = _EPS_LINE.search(line)
        if eps:
            ready, total = int(eps.group(2)), int(eps.group(3))
            for service in reversed(services):
                if service.ready_endpoints == 0 and service.not_ready_endpoints == 0:
                    service.ready_endpoints = ready
                    service.not_ready_endpoints = max(total - ready, 0)
                    break

    for service in services:
        service.status = "OK" if service.ready_endpoints >= 1 else "WARNING"
    return services


# --------------------------------------------------------------------------
# Certificates / storage (tab-separated metadata tables)
# --------------------------------------------------------------------------

_CERT_BLOCK = re.compile(r"^\[([A-Z_]+)\]\s+(\S+)\s+\|\s+namespace=(\S+)\s+\|")
_CERT_DAYS = re.compile(r"\bdaysLeft=(-?\d+)")
_CERT_CN = re.compile(r"CN\s*=\s*([^,]+)")


def _cert_status(days: int | None, fallback: str = "") -> str:
    if days is None:
        return canonical_severity(fallback)
    if days < 0 or days <= 7:
        return "CRITICAL"
    if days <= 30:
        return "WARNING"
    return "OK"


def _cert_field(value: str) -> str:
    match = _CERT_CN.search(value)
    return (match.group(1) if match else value).strip()


def normalize_certificates(lines: list[str], namespace: str = "") -> list[Certificate]:
    certs: list[Certificate] = []

    # Primary format: the engine's `TLS CERTIFICATE METADATA` block, e.g.
    #   [OK] demo-tls | namespace=default | source=Secret/tls.crt certificate#1 | daysLeft=364
    #   subject=CN = demo.sentinel.local, O = DevOpsSentinel Demo
    #   issuer=CN = demo.sentinel.local, O = DevOpsSentinel Demo
    #   notAfter=Oct  4 03:32:57 2027 GMT
    current: Certificate | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            certs.append(current)
            current = None

    for raw in lines:
        stripped = raw.strip()
        block = _CERT_BLOCK.match(stripped)
        if block:
            flush()
            state, name, ns = block.groups()
            days_match = _CERT_DAYS.search(stripped)
            days = int(days_match.group(1)) if days_match else None
            current = Certificate(
                name=name,
                namespace=ns or namespace,
                days=days,
                status=_cert_status(days, state),
            )
            continue
        if current is None:
            continue
        if stripped.startswith("subject="):
            current.cn = _cert_field(stripped[len("subject="):])
        elif stripped.startswith("issuer="):
            current.issuer = _cert_field(stripped[len("issuer="):])
        elif stripped.startswith("notAfter="):
            current.expiry = stripped[len("notAfter="):].strip()
    flush()

    # Fallback: tab-separated certificate tables (other engine revisions).
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if not any(h in low for h in ("certificate", "cn", "expiry", "days", "issuer", "not after")):
            continue
        if "name" not in low and "cn" not in low:
            continue
        for row in rows:
            name = _cell(row, header, "name", "certificate", "secret")
            cn = _cell(row, header, "cn", "common name", "subject")
            if not name and not cn:
                continue
            days_raw = _cell(row, header, "days", "remaining", "expires in")
            try:
                days = int(re.sub(r"[^0-9-]", "", days_raw)) if days_raw else None
            except ValueError:
                days = None
            if days is None:
                status = canonical_severity(_cell(row, header, "status"))
            elif days < 0:
                status = "CRITICAL"
            elif days <= 7:
                status = "CRITICAL"
            elif days <= 30:
                status = "WARNING"
            else:
                status = "OK"
            certs.append(
                Certificate(
                    name=name or cn,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    cn=cn,
                    issuer=_cell(row, header, "issuer", "ca"),
                    expiry=_cell(row, header, "not after", "expiry", "expires"),
                    days=days,
                    status=status,
                    consumers=int(re.sub(r"[^0-9]", "", _cell(row, header, "consumers")) or 0),
                    gitops=_cell(row, header, "gitops", "flux"),
                )
            )
    # Consumers: count Secret mount references reported by the engine
    # (`SECRET MOUNT REFERENCES` table) so PKI rows can show blast radius.
    mounts: dict[str, int] = {}
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "secret" in low and "pod" in low and any(h in low for h in ("mount path", "volume")):
            idx = low.index("secret")
            for row in rows:
                if idx < len(row) and row[idx].strip():
                    key = row[idx].strip()
                    mounts[key] = mounts.get(key, 0) + 1
    for cert in certs:
        if cert.name in mounts:
            cert.consumers = mounts[cert.name]
    return certs


_PVC_TREE = re.compile(r"^PVC/(\S+)\s+phase=(\S+)\s+requested=(\S+)\s+capacity=(\S+)")
_PVC_PV = re.compile(r"\bPV:\s*(\S+)\s+class=(\S+)")
_PVC_POD = re.compile(r"\bPod:\s*(\S+)\s+node=")


def normalize_pvcs(lines: list[str], namespace: str = "") -> list[PVC]:
    pvcs: list[PVC] = []

    # Primary format: the engine's `STORAGE DEPENDENCY GRAPH` tree, e.g.
    #   PVC/demo-data phase=Bound requested=1Gi capacity=1Gi
    #   ├── PV: pvc-0f1d... class=local-path reclaim=Delete csi=UNKNOWN
    #   └── Pod: demo-web-7cf4... node=dev
    current: PVC | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            pvcs.append(current)
            current = None

    for raw in lines:
        line = raw.strip()
        tree = _PVC_TREE.match(line)
        if tree:
            flush()
            name, phase, _requested, capacity = tree.groups()
            current = PVC(
                name=name,
                namespace=namespace,
                status=phase,
                capacity=capacity,
                severity="OK" if phase.lower() == "bound" else "WARNING",
            )
            continue
        if current is not None:
            pv = _PVC_PV.search(line)
            if pv:
                current.volume = pv.group(1)
                current.storage_class = pv.group(2)
            pod = _PVC_POD.search(line)
            if pod and pod.group(1) not in current.consumers:
                current.consumers.append(pod.group(1))
    flush()

    if pvcs:
        return pvcs

    # Fallback: tab-separated metadata tables (other engine revisions).
    for header, rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "name" not in low:
            continue
        if not any(
            h in low
            for h in ("capacity", "volume", "access modes", "storageclass", "storage class", "status")
        ):
            continue
        for row in rows:
            name = _cell(row, header, "name")
            if not name or name.upper() == "TOTALS":
                continue
            status = _cell(row, header, "status", "phase") or "Bound"
            pvcs.append(
                PVC(
                    name=name,
                    namespace=_cell(row, header, "namespace", "ns") or namespace,
                    status=status,
                    capacity=_cell(row, header, "capacity", "size"),
                    access_modes=_cell(row, header, "access modes", "access"),
                    storage_class=_cell(row, header, "storageclass", "storage class", "class"),
                    volume=_cell(row, header, "volume", "pv"),
                    severity="OK" if status.lower() == "bound" else "WARNING",
                )
            )
    return pvcs


# --------------------------------------------------------------------------
# Database / Kafka discovery tables (engine `--postgres-discovery`,
# `--kafka-discovery`). Both emit TAB-separated `SERVICE ...` tables.
# --------------------------------------------------------------------------

_UNKNOWN_MARKERS = ("", "-", "UNKNOWN")


def _known(value: str) -> bool:
    return value.strip().upper() not in _UNKNOWN_MARKERS and "UNKNOWN" not in value.upper()


def normalize_db_services(lines: list[str], namespace: str = "") -> list[DbService]:
    """Parse the engine's PostgreSQL / generic DB discovery table."""
    rows: list[DbService] = []
    for header, table_rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "service" not in low:
            continue
        if not any(h in low for h in ("ready endpoint", "database", "port")):
            continue
        for row in table_rows:
            name = _cell(row, header, "service", "name")
            if not name:
                continue
            ready = _cell(row, header, "ready endpoint")
            rows.append(
                DbService(
                    name=name,
                    namespace=namespace,
                    type=_cell(row, header, "type") or "ClusterIP",
                    port=_cell(row, header, "port"),
                    cluster_ip=_cell(row, header, "cluster ip"),
                    external_ip=_cell(row, header, "external ip"),
                    ready_endpoint=ready,
                    database=_cell(row, header, "database"),
                    username=_cell(row, header, "username"),
                    status="OK" if _known(ready) else "WARNING",
                )
            )
    return rows


def _kafka_bootstrap(name: str, namespace: str, ports: str) -> str:
    """Turn `kafka:9093` into a usable `kafka.<ns>.svc:9093` candidate."""
    first = ports.split(",")[0].strip() if ports else ""
    if not first:
        return ""
    _, _, port = first.partition(":")
    if not port.isdigit():
        return ""
    host = f"{name}.{namespace}.svc" if namespace else name
    return f"{host}:{port}"


def normalize_kafka_services(lines: list[str], namespace: str = "") -> list[KafkaService]:
    """Parse the engine's Kafka discovery table (`SERVICE TYPE CLUSTER IP PORTS`)."""
    rows: list[KafkaService] = []
    for header, table_rows in extract_tables(lines):
        low = [h.lower() for h in header]
        if "service" not in low or "ports" not in low:
            continue
        for row in table_rows:
            name = _cell(row, header, "service", "name")
            if not name:
                continue
            ports = _cell(row, header, "ports")
            rows.append(
                KafkaService(
                    name=name,
                    namespace=namespace,
                    type=_cell(row, header, "type") or "ClusterIP",
                    cluster_ip=_cell(row, header, "cluster ip"),
                    ports=ports,
                    bootstrap=_kafka_bootstrap(name, namespace, ports),
                    status="OK" if ports else "WARNING",
                )
            )
    return rows


# --------------------------------------------------------------------------
# Dependency graph + logs
# --------------------------------------------------------------------------

_ARROW = re.compile(r"([A-Za-z][A-Za-z0-9]*)/(\S+)\s*->\s*([A-Za-z][A-Za-z0-9]*)/(\S+?)(?:\s|$)")


def normalize_dependency_graph(lines: list[str]) -> Graph:
    """Parse `Kind/a -> Kind/b` chains (dependency and GitOps comparison lines)."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def add_node(kind: str, name: str) -> str:
        node_id = f"{kind}/{name}"
        nodes.setdefault(
            node_id,
            GraphNode(id=node_id, kind=kind, name=name, domain=_domain_for_kind(kind), state="UNKNOWN"),
        )
        return node_id

    for raw in lines:
        for match in _ARROW.finditer(raw):
            src = add_node(match.group(1), match.group(2).rstrip(":"))
            dst = add_node(match.group(3), match.group(4).rstrip(":"))
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
    for index, raw in enumerate(lines, start=1):
        low = raw.lower()
        level = "INFO"
        if "error" in low or "fatal" in low or "panic" in low:
            level = "ERROR"
        elif "warn" in low:
            level = "WARN"
        elif "debug" in low or "trace" in low:
            level = "DEBUG"
        out.append(LogLine(n=index, text=raw, level=level))
        normalized = re.sub(r"\d+", "#", raw.strip())[:120]
        if normalized:
            counts[normalized] = counts.get(normalized, 0) + 1
    patterns = [
        {"pattern": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda kv: -kv[1])[:10]
        if value > 1
    ]
    return LogBundle(pod=pod, container=container, previous=previous, lines=out, patterns=patterns)







