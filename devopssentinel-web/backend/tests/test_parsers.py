"""Parser/normalizer tests using representative engine report lines."""

from __future__ import annotations

from app.services.parsers import (
    canonical_severity,
    normalize_capabilities,
    normalize_certificates,
    normalize_dependency_graph,
    normalize_findings,
    normalize_gitops,
    normalize_logs,
    normalize_pods,
    normalize_pvcs,
    normalize_services,
    normalize_workloads,
)

POD_LINES = [
    "NAME                 READY   STATUS             RESTARTS   NODE      AGE",
    "transformer-abc      1/1     Running            0          node-1    5d",
    "log-transformer-def  0/1     CrashLoopBackOff   7          node-2    2h",
]


def test_canonical_severity_mapping():
    assert canonical_severity("CrashLoopBackOff") == "CRITICAL"
    assert canonical_severity("Running") == "OK"
    assert canonical_severity("Pending") == "WARNING"
    assert canonical_severity("NotProbed") == "UNKNOWN"


def test_normalize_pods():
    pods = normalize_pods(POD_LINES, "etdp")
    assert len(pods) == 2
    crashed = [p for p in pods if p.name == "log-transformer-def"][0]
    assert crashed.restarts == 7
    assert crashed.status == "CRITICAL"
    assert crashed.namespace == "etdp"


def test_normalize_workloads():
    rows = normalize_workloads(POD_LINES, "etdp")
    assert rows and rows[0].kind


def test_normalize_certificates_computes_status():
    lines = [
        "NAME           NAMESPACE   CN               ISSUER        EXPIRY      DAYS   CONSUMERS",
        "syslog-cert    etdp        syslog.local     internal-ca   2026-11-01  29     3",
        "expired-cert   etdp        old.local        internal-ca   2026-01-01  -5     0",
    ]
    certs = normalize_certificates(lines, "etdp")
    assert len(certs) == 2
    by_name = {c.name: c for c in certs}
    assert by_name["syslog-cert"].status == "WARNING"
    assert by_name["expired-cert"].status == "CRITICAL"
    assert by_name["syslog-cert"].consumers == 3


def test_normalize_gitops_ready_flag():
    lines = [
        "NAME          READY   REVISION           APPLIED            KIND",
        "devopsonm     True    main@sha1:7ac901b  main@sha1:7ac901b  Kustomization",
        "transformer   False   main@sha1:7ac901b  main@sha1:7ac901a  HelmRelease",
    ]
    objs = normalize_gitops(lines, "flux-system")
    by_name = {o.name: o for o in objs}
    assert by_name["devopsonm"].ready is True
    assert by_name["transformer"].ready is False
    assert by_name["transformer"].kind == "HelmRelease"


def test_normalize_services_and_endpoint_gaps():
    lines = [
        "NAME         TYPE        CLUSTERIP   READY   PORTS",
        "transformer  ClusterIP   10.0.0.5    2      8443/TCP",
        "syslog-svc   ClusterIP   10.0.0.6    0      514/UDP",
    ]
    svcs = normalize_services(lines, "etdp")
    assert len(svcs) == 2
    gaps = [s for s in svcs if s.ready_endpoints == 0]
    assert gaps and gaps[0].name == "syslog-svc"


def test_normalize_pvcs():
    lines = [
        "NAME         STATUS   CAPACITY   STORAGECLASS",
        "data-0       Bound    10Gi       standard",
        "data-1       Pending  10Gi       standard",
    ]
    pvcs = normalize_pvcs(lines, "etdp")
    by_name = {p.name: p for p in pvcs}
    assert by_name["data-0"].severity == "OK"
    assert by_name["data-1"].severity == "WARNING"


def test_normalize_findings_extracts_resource():
    lines = ["CRITICAL  Pod/log-transformer-def  CrashLoopBackOff  exit code 1"]
    findings = normalize_findings(lines, "etdp")
    assert len(findings) == 1
    assert findings[0].severity == "CRITICAL"
    assert findings[0].resource == "Pod/log-transformer-def"
    assert findings[0].domain == "Workload"


def test_normalize_capabilities():
    lines = ["kubectl              AVAILABLE    v1.29.0", "Metrics API          UNAVAILABLE  OPTIONAL"]
    caps = normalize_capabilities(lines)
    assert len(caps) == 2
    assert caps[0].status == "AVAILABLE"
    assert caps[1].optional is True


def test_normalize_dependency_graph():
    lines = ["Pod/transformer-abc -> ReplicaSet/transformer-xyz -> Deployment/transformer"]
    graph = normalize_dependency_graph(lines)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2
    assert graph.edges[0].label == "OWNS"


def test_normalize_logs_detects_levels_and_patterns():
    lines = ["ERROR certificate verify failed", "ERROR certificate verify failed", "INFO started"]
    bundle = normalize_logs(lines, "pod-x")
    assert bundle.lines[0].level == "ERROR"
    assert bundle.patterns and bundle.patterns[0]["count"] == 2
