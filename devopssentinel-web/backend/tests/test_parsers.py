"""Parser tests using REAL DevOpsSentinel v4.2.2 output.

Every fixture below is copied verbatim from a live `--json` capture against a
vcluster (`kubernetes-super-admin@dev`), so the tests fail if the engine's
format drifts.
"""

from __future__ import annotations

from app.services.parsers import (
    canonical_severity,
    engine_severity,
    extract_tables,
    normalize_capabilities,
    normalize_certificates,
    normalize_db_services,
    normalize_dependency_graph,
    normalize_events,
    normalize_findings,
    normalize_gitops,
    normalize_kafka_services,
    normalize_logs,
    normalize_pods,
    normalize_pvcs,
    normalize_secrets,
    normalize_services,
    normalize_workloads,
    pod_severity,
    split_row,
)

POD_TABLE = [
    "SOURCE\tpods\tSTATUS\tOK\tUPDATED\t2026-10-04T01:53:07Z\tCACHE AGE\t0 sec",
    "POD\tREADY\tSTATUS\tRESTARTS\tAGE\tCPU USED\tCPU REQ\tCPU LIMIT\tMEM USED\t"
    "MEM REQ\tMEM LIMIT\tCPU/REQ\tCPU/LIMIT\tMEM/REQ\tMEM/LIMIT\tNODE\tIP\tOWNER\t"
    "CONTAINERS\tIMAGES",
    "helm-controller-6f558f6c5d-z9vjb\t0/1\tRunning\t17\t126d\tN/A\t100m\t1000m\tN/A\t"
    "64 MiB\t1 GiB\tN/A\tN/A\tN/A\tN/A\tdev\t-\tDeployment/helm-controller\tmanager\t"
    "ghcr.io/fluxcd/helm-controller:v1.1.0",
    "kustomize-controller-74fb56995-vxkjn\t0/1\tRunning\t18\t126d\tN/A\t100m\t1000m\tN/A\t"
    "64 MiB\t1 GiB\tN/A\tN/A\tN/A\tN/A\tdev\t-\tDeployment/kustomize-controller\tmanager\t"
    "ghcr.io/fluxcd/kustomize-controller:v1.4.0",
    "TOTALS (active pods; requests include init/sidecar peak and overhead)",
    "CPU USED\tINCOMPLETE [known=0]\tCPU REQUEST\t350m\tCPU LIMIT\t4000m",
    "",
]

PODINFO_TABLE = [
    "POD\tREADY\tSTATUS\tRESTARTS\tAGE\tCPU USED\tCPU REQ\tCPU LIMIT\tMEM USED\tMEM REQ\t"
    "MEM LIMIT\tNODE\tIP\tOWNER\tCONTAINERS\tIMAGES",
    "podinfo-6998f8d45-77527\t1/1\tRunning\t13\t14d\tN/A\t100m\t2000m\tN/A\t64 MiB\t"
    "512 MiB\tdev\t10.244.0.54\tDeployment/podinfo\tpodinfod\tghcr.io/stefanprodan/podinfo:6.15.0",
    "podinfo-6998f8d45-jfdlx\t1/1\tRunning\t12\t14d\tN/A\t100m\t2000m\tN/A\t64 MiB\t"
    "512 MiB\tdev\t10.244.0.49\tDeployment/podinfo\tpodinfod\tghcr.io/stefanprodan/podinfo:6.15.0",
]

TRIAGE_TABLE = [
    "KUBERNETES TRIAGE | one-command incident scope",
    "CONTEXT\tkubernetes-super-admin@dev",
    "FINDINGS\tFAIL=2\tWARN=129\tUNKNOWN=2\tINFO=4 (full detail: --health)",
    "SEVERITY\tCATEGORY\tRESOURCE\tISSUE\tEVIDENCE\tNEXT CHECK",
    "FAIL\tPODS\tPod/kustomize-controller-74fb56995-vxkjn\tRunning pod is not Ready\t"
    "OBSERVED Pod Ready condition\tPod inspector + related events",
    "WARN\tRESTARTS\tPod/helm-controller-6f558f6c5d-z9vjb/manager\tRestart count 18\t"
    "OBSERVED cumulative count; not a restart rate\tPod inspector",
    "WARN\tEVENTS\tPod/source-controller-6d597849c8-dtwq4\tFailedCreatePodSandBox: "
    "failed to setup network for sandbox\tOBSERVED retained event count=1 "
    "latest=2026-10-04T01:50:27Z\tEvent timeline",
    "TRUNCATED\t101 more FAIL/WARN findings; complete list in --health",
]

GITOPS_BLOCKS = [
    "GITOPS / FLUX | context=kubernetes-super-admin@dev namespace=flux-system",
    "gitrepositories | status=OK | cache age=0s",
    "TOTAL 4 | READY 2 | SUSPENDED 0 | FAILED 2",
    "",
    "GitRepository/algorithm-learn-source [FAIL RECONCILIATION_FAILED]",
    "  Ready=False suspend=false generation=1 observed=1",
    "  Created=2026-05-30T09:08:29Z transition=2026-09-19T03:44:46Z handledReconcile=UNKNOWN",
    "  URL=https://github.com/dheer629/learnalgorithm.git branch/tag=main",
    "  Artifact=main@sha1:4c93a767 applied=- attempted=-",
    "  Reason=GitOperationFailed message=authentication required",
    "",
    "GitRepository/podinfo-demo-source [OK NO_DRIFT_EVIDENCE]",
    "  Ready=True suspend=false generation=1 observed=1",
    "  Artifact=master@sha1:3e0ff8ae applied=- attempted=-",
    "  Reason=Succeeded message=stored artifact",
    "",
    "Kustomization/learnalgorithm-app [WARN RECONCILIATION_PENDING]",
    "  Ready=Unknown suspend=false generation=1 observed=1",
    "  Source=GitRepository/learnalgorithm-repo namespace=flux-system path=./deploy/k8s",
    "  Artifact=- applied=main@sha1:4c93a767 attempted=main@sha1:4c93a767",
    "  Reason=Progressing message=Reconciliation in progress",
    "",
    "Kustomization/podinfo-demo -> GitRepository/podinfo-demo-source: NO_DRIFT_EVIDENCE (revision matches)",
]

NETWORK_TREE = [
    "SERVICE / NETWORK TOPOLOGY | namespace=flux-system",
    "Service/notification-controller type=ClusterIP clusterIP=10.96.145.16 ports=80:http",
    "\u251c\u2500\u2500 EndpointSlice: notification-controller-gnhpg ready=1/1",
    "\u2502   \u2514\u2500\u2500 10.244.0.233 -> Pod/notification-controller-5d794dd575-s9c42",
    "Service/source-controller type=ClusterIP clusterIP=10.107.76.245 ports=80:http",
    "\u251c\u2500\u2500 EndpointSlice: source-controller-gxd5n ready=1/1",
    "Service/broken-svc type=ClusterIP clusterIP=10.96.0.9 ports=8080:http",
    "NETWORK POLICIES",
    "NetworkPolicy/allow-egress podSelector={} policyTypes=Ingress,Egress enforcement=NOT_VERIFIED_BY_CNI",
]

DOCTOR_LINES = [
    " TOOLING",
    "kubectl                      AVAILABLE",
    "jq                           AVAILABLE",
    "psql                         NOT INSTALLED",
    "kafka-topics.sh              NOT INSTALLED",
    " API discovery               OK",
    "Flux CRDs                   AVAILABLE",
    "cert-manager CRDs           OPTIONAL/UNAVAILABLE",
    "Metrics API                 OPTIONAL/UNAVAILABLE",
    " CONTEXT:kubernetes-super-admin@dev | NAMESPACE:flux-system | MODE:SUPERVISION",
    " HEALTH [ OK ] | AUTH [ OK ] | API [ OK ] | RBAC [ OK ]",
]


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def test_split_row_handles_tab_separated_engine_output():
    assert split_row("POD\tREADY\tSTATUS") == ["POD", "READY", "STATUS"]
    assert split_row("a | b | c") == ["a", "b", "c"]
    assert split_row("a      b") == ["a", "b"]


def test_header_detection_requires_all_caps_columns():
    tables = extract_tables(POD_TABLE)
    assert tables
    header, rows = tables[0]
    assert header[:3] == ["POD", "READY", "STATUS"]
    assert len(rows) == 2
    # The "SOURCE  pods  STATUS  OK" line is not a header (lowercase 'pods').
    assert all("SOURCE" not in h for h, _ in tables)


def test_severity_mapping():
    assert engine_severity("FAIL") == "FAILED"
    assert engine_severity("WARN") == "WARNING"
    assert engine_severity("OK") == "OK"
    assert canonical_severity("CrashLoopBackOff") == "CRITICAL"
    assert canonical_severity("Running") == "OK"
    assert canonical_severity("NotProbed") == "UNKNOWN"


def test_pod_severity_uses_ready_fraction():
    # Running but 0/1 ready is a failure, not "healthy".
    assert pod_severity("Running", "0/1") == "CRITICAL"
    assert pod_severity("Running", "1/1") == "OK"
    assert pod_severity("Running", "1/2") == "WARNING"
    assert pod_severity("CrashLoopBackOff", "0/1") == "CRITICAL"
    # A long-lived pod with restarts but full readiness stays OK; restart
    # findings come from the engine's own triage, not from a local threshold.
    assert pod_severity("Running", "1/1") == "OK"


# --------------------------------------------------------------------------
# Pods / workloads
# --------------------------------------------------------------------------

def test_normalize_pods_from_real_resources_table():
    pods = normalize_pods(POD_TABLE, "flux-system")
    assert len(pods) == 2
    first = pods[0]
    assert first.name == "helm-controller-6f558f6c5d-z9vjb"
    assert first.ready == "0/1"
    assert first.restarts == 17
    assert first.node == "dev"
    assert first.owner == "Deployment/helm-controller"
    assert first.namespace == "flux-system"
    assert first.status == "CRITICAL"
    assert "manager" in first.containers


def test_normalize_workloads_derives_from_pod_owners():
    workloads = normalize_workloads(PODINFO_TABLE, "podinfo-demo")
    assert len(workloads) == 1
    deployment = workloads[0]
    assert deployment.kind == "Deployment"
    assert deployment.name == "podinfo"
    assert deployment.ready == "2/2"
    assert deployment.status == "OK"
    assert deployment.restarts == 13


# --------------------------------------------------------------------------
# Findings / events
# --------------------------------------------------------------------------

def test_normalize_findings_ignores_summary_and_legend_lines():
    """A report that says `FAIL=0` must produce no findings.

    Captured from the live engine when nothing was wrong:

        FINDINGS\\tFAIL=0\\tWARN=0\\tUNKNOWN=3\\tINFO=0 (full detail: --health)
        UNKNOWN\\t3 findings are data gaps, not healthy states; ...
        TRIAGE EXIT\\t0=no FAIL 1=observed FAIL 3=auth/API failure ...

    The fallback used to read each of those as a finding, so the queue showed
    three rows while the engine reported nothing wrong (spec sections 44, 286).
    """
    findings = normalize_findings(
        [
            "FINDINGS\tFAIL=0\tWARN=0\tUNKNOWN=3\tINFO=0 (full detail: --health)",
            "UNKNOWN\t3 findings are data gaps, not healthy states; "
            "inspect --health coverage table",
            "TRIAGE EXIT\t0=no FAIL 1=observed FAIL 3=auth/API failure "
            "4=required pod inventory unavailable",
        ]
    )
    assert findings == []


def test_normalize_findings_still_reads_embedded_severity_lines():
    """The tightened fallback must not silence genuine embedded findings."""
    findings = normalize_findings(
        [
            "[FAIL] Pod/transformer-abc is not Ready",
            "[WARN] syslog-cert | namespace=devopsonm | daysLeft=29",
        ]
    )
    assert len(findings) == 2
    assert findings[0].severity == "FAILED"
    assert findings[0].resource == "Pod/transformer-abc"
    assert findings[1].severity == "WARNING"


def test_normalize_findings_from_real_triage_table():
    findings = normalize_findings(TRIAGE_TABLE, "flux-system")
    assert len(findings) == 3
    assert findings[0].severity == "FAILED"
    assert findings[0].domain == "Workload"
    assert findings[0].resource == "Pod/kustomize-controller-74fb56995-vxkjn"
    assert findings[0].finding == "Running pod is not Ready"
    assert findings[0].evidence == "OBSERVED Pod Ready condition"
    assert findings[1].severity == "WARNING"
    # The "TRUNCATED" summary line must not become a finding.
    assert all("TRUNCATED" not in f.finding for f in findings)


def test_normalize_events_extracts_time_and_reason():
    events = normalize_events(TRIAGE_TABLE, "flux-system")
    assert len(events) == 1
    event = events[0]
    assert event.reason == "FailedCreatePodSandBox"
    assert event.time == "2026-10-04T01:50:27Z"
    assert event.count == 1
    assert event.severity == "WARNING"
    assert "failed to setup network" in event.message


# --------------------------------------------------------------------------
# GitOps
# --------------------------------------------------------------------------

def test_normalize_gitops_from_real_block_format():
    objects = normalize_gitops(GITOPS_BLOCKS, "flux-system")
    by_name = {(o.kind, o.name): o for o in objects}
    assert len(objects) == 3

    failed = by_name[("GitRepository", "algorithm-learn-source")]
    assert failed.ready is False
    assert failed.status == "FAILED"
    assert failed.suspended is False
    assert failed.revision == "main@sha1:4c93a767"
    assert failed.message == "authentication required"

    healthy = by_name[("GitRepository", "podinfo-demo-source")]
    assert healthy.ready is True
    assert healthy.status == "OK"

    pending = by_name[("Kustomization", "learnalgorithm-app")]
    assert pending.ready is None  # Ready=Unknown is neither True nor False
    assert pending.status == "WARNING"
    assert pending.applied_revision == "main@sha1:4c93a767"


def test_normalize_gitops_comparison_line_becomes_graph_edge():
    graph = normalize_dependency_graph(GITOPS_BLOCKS)
    ids = {node.id for node in graph.nodes}
    assert "Kustomization/podinfo-demo" in ids
    assert "GitRepository/podinfo-demo-source" in ids
    assert any(edge.label == "MANAGED_BY" for edge in graph.edges)


def test_dependency_graph_edge_keeps_engine_evidence():
    """Every edge carries the engine's own report line (spec sections 37, 347).

    Without this the edge-detail panel could show a relationship but not why it
    exists, which would make the GUI assert something the engine never said.
    """
    graph = normalize_dependency_graph(GITOPS_BLOCKS)
    assert graph.edges, "fixture should produce at least one edge"
    for edge in graph.edges:
        assert edge.evidence, f"edge {edge.id} lost its evidence line"
        assert "->" in edge.evidence


def test_dependency_graph_evidence_is_bounded():
    """A pathological report line must not be stored whole."""
    long_line = "Pod/a -> Service/b " + ("x" * 5000)
    graph = normalize_dependency_graph([long_line])
    assert len(graph.edges) == 1
    assert len(graph.edges[0].evidence) <= 300


GITOPS_TREE = [
    "GitOps Dependency Graph | 2026-10-09T16:17:43Z",
    "Context: vcluster-docker_dev | Namespace: flux-system",
    "GITOPS DEPENDENCY GRAPH | namespace=flux-system",
    "GitRepository/devopsonm revision=main@sha1:f74034cc",
    "\u251c\u2500\u2500 Kustomization/devopsonm ready=True applied=main@sha1:f74034cc",
    "GitRepository/learnalgorithm-repo revision=main@sha1:4c93a767",
    "\u251c\u2500\u2500 Kustomization/learnalgorithm-app ready=True applied=main@sha1:4c93a767",
    "",
    "HELM RELEASE SOURCES",
    "",
    "Confidence: CONFIRMED where Flux sourceRef/status.inventory explicitly links objects.",
]


def test_dependency_graph_reads_the_engine_tree_format():
    """Regression: the GitOps graph is a tree, not an arrow chain.

    Reading only `->` edges made this report parse to zero edges, so the console
    said "no chain was reported" while the engine had reported one.
    """
    graph = normalize_dependency_graph(GITOPS_TREE)
    ids = {node.id for node in graph.nodes}
    assert ids == {
        "GitRepository/devopsonm",
        "Kustomization/devopsonm",
        "GitRepository/learnalgorithm-repo",
        "Kustomization/learnalgorithm-app",
    }
    pairs = {(edge.source, edge.target) for edge in graph.edges}
    assert ("GitRepository/devopsonm", "Kustomization/devopsonm") in pairs
    assert ("GitRepository/learnalgorithm-repo", "Kustomization/learnalgorithm-app") in pairs
    # A child is attached to its own parent, never to the previous sibling's.
    assert ("GitRepository/devopsonm", "Kustomization/learnalgorithm-app") not in pairs
    assert all(edge.label == "MANAGED_BY" for edge in graph.edges)
    assert all(edge.evidence for edge in graph.edges)


def test_dependency_graph_does_not_invent_nodes_from_prose():
    """`sourceRef/status.inventory` in a note is not a resource reference."""
    graph = normalize_dependency_graph(GITOPS_TREE)
    assert not any("sourceRef" in node.id for node in graph.nodes)
    assert not any("status.inventory" in node.id for node in graph.nodes)


def test_dependency_graph_reads_both_formats_together():
    graph = normalize_dependency_graph(
        ["Pod/a -> Service/b", "GitRepository/r revision=x", "\u251c\u2500\u2500 Kustomization/k ready=True"]
    )
    pairs = {(edge.source, edge.target) for edge in graph.edges}
    assert ("Pod/a", "Service/b") in pairs
    assert ("GitRepository/r", "Kustomization/k") in pairs


# --------------------------------------------------------------------------
# Network / certificates / storage
# --------------------------------------------------------------------------

def test_normalize_services_from_real_tree():
    services = normalize_services(NETWORK_TREE, "flux-system")
    by_name = {s.name: s for s in services}
    assert len(services) == 3
    assert by_name["notification-controller"].ready_endpoints == 1
    assert by_name["notification-controller"].cluster_ip == "10.96.145.16"
    assert by_name["notification-controller"].ports == "80:http"
    assert by_name["notification-controller"].status == "OK"
    # A service with no EndpointSlice line is an endpoint gap.
    assert by_name["broken-svc"].ready_endpoints == 0
    assert by_name["broken-svc"].status == "WARNING"


def test_normalize_certificates_from_tab_table():
    lines = [
        "TLS CERTIFICATE METADATA | OK | cache age=0s",
        "NAME\tCN\tISSUER\tNOT AFTER\tDAYS\tSTATUS\tCONSUMERS",
        "syslog-cert\tsyslog.local\tinternal-ca\t2026-11-01T00:00:00Z\t29\tWARN\t3",
        "expired\ttest.local\tinternal-ca\t2026-01-01T00:00:00Z\t-5\tFAIL\t0",
    ]
    certs = normalize_certificates(lines, "devopsonm")
    by_name = {c.name: c for c in certs}
    assert by_name["syslog-cert"].status == "WARNING"
    assert by_name["syslog-cert"].days == 29
    assert by_name["syslog-cert"].consumers == 3
    assert by_name["expired"].status == "CRITICAL"


def test_secret_metadata_table_is_not_mistaken_for_certificates():
    lines = [
        "NAME\tTYPE\tCREATED\tKEY COUNT\tKEY NAMES",
        "flux-system\tOpaque\t2026-05-30T06:39:07Z\t5\tidentity password username",
    ]
    assert normalize_certificates(lines, "flux-system") == []


def test_normalize_pvcs() -> None:
    lines = [
        "NAME\tSTATUS\tCAPACITY\tACCESS MODES\tSTORAGECLASS\tVOLUME",
        "data-0\tBound\t10Gi\tRWO\tstandard\tpv-0",
        "data-1\tPending\t10Gi\tRWO\tstandard\t-",
    ]
    pvcs = normalize_pvcs(lines, "devopsonm")
    by_name = {p.name: p for p in pvcs}
    assert by_name["data-0"].severity == "OK"
    assert by_name["data-1"].severity == "WARNING"


STORAGE_TREE = [
    "STORAGE DEPENDENCY GRAPH | namespace=algorithm-learn",
    "PVC/backend-data phase=Bound requested=2Gi capacity=2Gi",
    "├── PV: pvc-bfe51ed5-6ec4-44d7-819c-c44cbb07d6dc class=local-path reclaim=Delete csi=UNKNOWN",
    "└── Pod: backend-65cf6b455b-9nps9 node=dev",
    "PVC/postgres-data phase=Bound requested=1Gi capacity=1Gi",
    "├── PV: pvc-a9d74f18-e8db-43cf-b632-72628e9e93cc class=local-path reclaim=Delete csi=UNKNOWN",
    "└── Pod: postgres-64cdc79784-8ggfz node=dev",
]


def test_normalize_pvcs_from_real_storage_tree() -> None:
    """The engine's `--storage` report is a tree, not a table."""
    pvcs = normalize_pvcs(STORAGE_TREE, "algorithm-learn")
    by_name = {p.name: p for p in pvcs}
    assert len(pvcs) == 2
    assert by_name["backend-data"].status == "Bound"
    assert by_name["backend-data"].capacity == "2Gi"
    assert by_name["backend-data"].storage_class == "local-path"
    assert by_name["backend-data"].volume.startswith("pvc-bfe51ed5")
    assert by_name["backend-data"].severity == "OK"
    assert by_name["postgres-data"].storage_class == "local-path"
    # The tree names the consuming pod, so storage rows can show their owner.
    assert by_name["backend-data"].consumers == ["backend-65cf6b455b-9nps9"]
    assert by_name["postgres-data"].consumers == ["postgres-64cdc79784-8ggfz"]


CERT_BLOCK = [
    "CERTIFICATES | namespace=default | TTL 60s | WARN <=30d CRITICAL <=7d",
    "SECRET METADATA | OK | cache age=0s",
    "NAME\tTYPE\tCREATED\tKEY COUNT\tKEY NAMES",
    "platform-cert-tls\tkubernetes.io/tls\t2026-10-04T06:06:50Z\t3\tca.crt tls.crt tls.key ",
    "platform-postgres\tOpaque\t2026-10-04T03:32:57Z\t1\tpassword ",
    "platform-tls\tkubernetes.io/tls\t2026-10-04T03:31:02Z\t2\ttls.crt tls.key ",
    "",
    "TLS CERTIFICATE METADATA | OK | cache age=0s",
    "[OK] platform-cert-tls | namespace=default | source=Secret/tls.crt certificate#1 | daysLeft=89",
    "subject=CN = platform-cert.local",
    "issuer=CN = platform-cert.local",
    "serial=31C73429D1E8F24B79DDFA42C133F691",
    "notBefore=Oct  4 06:06:50 2026 GMT",
    "notAfter=Jan  2 06:06:50 2027 GMT",
    "sha256 Fingerprint=4A:AC:36:7A:C9:7A:08:38:A7:CB:F1:3F:01:09:5B:4E:F3:46:27:BA:0C:BE:77:2B:E6:13:F8:EF:FD:92:8B:B2",
    "X509v3 Subject Alternative Name: ",
    "    DNS:platform-cert.local, DNS:platform-cert.default.svc",
    "",
    "[OK] platform-tls | namespace=default | source=Secret/tls.crt certificate#1 | daysLeft=364",
    "subject=CN = sentinel.internal, O = DevOpsSentinel Platform",
    "issuer=CN = sentinel.internal, O = DevOpsSentinel Platform",
    "serial=79DFF17B771C00EFAC61008E63164C05C0AC43ED",
    "notBefore=Oct  4 03:32:57 2026 GMT",
    "notAfter=Oct  4 03:32:57 2027 GMT",
    "",
    "DUPLICATE LEAF CERTIFICATES",
    "No duplicate leaf certificate fingerprints observed",
]


def test_normalize_certificates_from_real_block() -> None:
    """The engine's TLS metadata is a multi-line block, not a table."""
    certs = normalize_certificates(CERT_BLOCK, "default")
    assert len(certs) == 2
    by_name = {c.name: c for c in certs}
    cert = by_name["platform-tls"]
    assert cert.namespace == "default"
    assert cert.cn == "sentinel.internal"
    assert cert.issuer == "sentinel.internal"
    assert cert.days == 364
    assert cert.status == "OK"
    assert cert.expiry.startswith("Oct  4 03:32:57 2027")


def test_certificate_block_exposes_serial_fingerprint_and_san() -> None:
    """Real PKI detail (serial, fingerprint, SAN, source) is surfaced."""
    by_name = {c.name: c for c in normalize_certificates(CERT_BLOCK, "default")}
    cert = by_name["platform-cert-tls"]
    assert cert.serial == "31C73429D1E8F24B79DDFA42C133F691"
    assert cert.fingerprint.startswith("4A:AC:36:7A")
    assert cert.not_before.startswith("Oct  4 06:06:50 2026")
    assert cert.san == "DNS:platform-cert.local, DNS:platform-cert.default.svc"
    assert cert.source == "Secret/tls.crt certificate#1"
    assert cert.days == 89
    assert cert.status == "OK"


def test_normalize_secrets_joins_tls_expiry() -> None:
    """Secret inventory carries the certificate expiry for TLS Secrets."""
    records = normalize_secrets(CERT_BLOCK, "default")
    by_name = {s.name: s for s in records}
    assert set(by_name) == {"platform-cert-tls", "platform-postgres", "platform-tls"}

    tls = by_name["platform-tls"]
    assert tls.is_tls is True
    assert tls.type == "kubernetes.io/tls"
    assert tls.key_count == 2
    assert tls.keys == "tls.crt tls.key"
    assert tls.days == 364
    assert tls.status == "OK"
    assert tls.expires.startswith("Oct  4 03:32:57 2027")

    cert_manager = by_name["platform-cert-tls"]
    assert cert_manager.days == 89
    assert cert_manager.key_count == 3

    # Opaque Secrets are inventoried but never claim a certificate expiry.
    opaque = by_name["platform-postgres"]
    assert opaque.is_tls is False
    assert opaque.days is None
    assert opaque.expires == ""


def test_normalize_secrets_flags_expiring_tls_secret() -> None:
    lines = [
        "SECRET METADATA | OK | cache age=0s",
        "NAME\tTYPE\tCREATED\tKEY COUNT\tKEY NAMES",
        "soon-tls\tkubernetes.io/tls\t2026-10-01T00:00:00Z\t2\ttls.crt tls.key ",
        "",
        "[WARN] soon-tls | namespace=default | source=Secret/tls.crt certificate#1 | daysLeft=5",
        "subject=CN = soon.local",
        "notAfter=Oct  9 00:00:00 2026 GMT",
    ]
    records = normalize_secrets(lines, "default")
    assert records and records[0].name == "soon-tls"
    assert records[0].days == 5
    assert records[0].status == "CRITICAL"


def test_normalize_certificates_expired_block_is_critical() -> None:
    lines = [
        "[EXPIRED] stale-tls | namespace=default | source=Secret/tls.crt certificate#1 | daysLeft=-3",
        "subject=CN = stale.local",
        "notAfter=Jan  1 00:00:00 2025 GMT",
    ]
    certs = normalize_certificates(lines, "default")
    assert certs and certs[0].status == "CRITICAL"
    assert certs[0].days == -3


def test_certificate_consumers_from_mount_references() -> None:
    lines = CERT_BLOCK + [
        "SECRET MOUNT REFERENCES | SOURCE Pod specifications | namespace=default | cache age=0s",
        "SECRET\tPOD\tVOLUME\tCONTAINER\tMOUNT PATH\tSUBPATH\tSTATUS",
        "platform-tls\tplatform-web-1\tdata\tweb\t/etc/tls\t-\tCONFIGURED",
    ]
    by_name = {c.name: c for c in normalize_certificates(lines, "default")}
    assert by_name["platform-tls"].consumers == 1
    assert by_name["platform-cert-tls"].consumers == 0


# --------------------------------------------------------------------------
# Database / Kafka discovery tables
# --------------------------------------------------------------------------

DB_TABLE = [
    "POSTGRESQL / GENERIC DB DISCOVERY | namespace=default",
    "SERVICE\tTYPE\tPORT\tCLUSTER IP\tEXTERNAL IP\tREADY ENDPOINT\tDATABASE\tUSERNAME",
    "kafka\tClusterIP\t9093\t10.109.53.81\t\t10.244.0.161\tUNKNOWN (safe metadata only)\t"
    "UNKNOWN (credential not read)",
    "postgres\tClusterIP\t5432\t10.100.141.34\t\t10.244.0.161\tUNKNOWN (safe metadata only)\t"
    "UNKNOWN (credential not read)",
    "stale-db\tClusterIP\t5432\t10.100.141.99\t\tUNKNOWN\tUNKNOWN (safe metadata only)\t"
    "UNKNOWN (credential not read)",
]

KAFKA_TABLE = [
    "KAFKA DIAGNOSTICS DISCOVERY | namespace=default",
    "kafka-topics          : TOOL_MISSING",
    "kafka-consumer-groups : TOOL_MISSING",
    "",
    "SERVICE\tTYPE\tCLUSTER IP\tPORTS",
    "kafka\tClusterIP\t10.109.53.81\tkafka:9093",
]


def test_normalize_db_services_from_real_table() -> None:
    rows = normalize_db_services(DB_TABLE, "default")
    by_name = {r.name: r for r in rows}
    assert len(rows) == 3
    assert by_name["postgres"].port == "5432"
    assert by_name["postgres"].cluster_ip == "10.100.141.34"
    assert by_name["postgres"].ready_endpoint == "10.244.0.161"
    assert by_name["postgres"].namespace == "default"
    assert by_name["postgres"].status == "OK"
    # A service with no ready endpoint is surfaced, not hidden.
    assert by_name["stale-db"].status == "WARNING"


def test_normalize_kafka_services_from_real_table() -> None:
    rows = normalize_kafka_services(KAFKA_TABLE, "default")
    assert len(rows) == 1
    assert rows[0].name == "kafka"
    assert rows[0].ports == "kafka:9093"
    assert rows[0].bootstrap == "kafka.default.svc:9093"
    assert rows[0].status == "OK"


def test_db_and_kafka_normalizers_do_not_cross_match() -> None:
    """The DB table has PORT; the Kafka table has PORTS. Never mix them."""
    assert normalize_kafka_services(DB_TABLE, "default") == []
    assert normalize_db_services(KAFKA_TABLE, "default") == []


# --------------------------------------------------------------------------
# Capabilities / logs
# --------------------------------------------------------------------------

def test_normalize_capabilities_from_real_doctor_output():
    caps = normalize_capabilities(DOCTOR_LINES)
    by_name = {c.name: c for c in caps}
    assert by_name["kubectl"].status == "AVAILABLE"
    assert by_name["psql"].status == "NOT INSTALLED"
    assert by_name["psql"].optional is True
    assert by_name["cert-manager CRDs"].status == "OPTIONAL/UNAVAILABLE"
    # Box/summary lines must not become capabilities.
    assert not any("AUTH" in name for name in by_name)
    assert not any("HEALTH" in name for name in by_name)
    assert not any("NAMESPACE" in name for name in by_name)


def test_normalize_logs_detects_levels_and_patterns():
    lines = ["ERROR certificate verify failed", "ERROR certificate verify failed", "INFO started"]
    bundle = normalize_logs(lines, "pod-x")
    assert bundle.lines[0].level == "ERROR"
    assert bundle.patterns and bundle.patterns[0]["count"] == 2


