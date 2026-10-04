"""Cross-platform fake DevOpsSentinel engine used by the backend tests.

It mirrors the real engine's ``--json`` contract exactly:
``{schema_version, application, tool_version, version, title, context,
namespace, timestamp, collected, exit_status, lines:[...]}``.
"""

from __future__ import annotations

import json
import sys
import time


def parse(args: list[str]) -> dict:
    out = {"context": "", "namespace": "", "mode": "dashboard", "json": False, "value": ""}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--context":
            out["context"] = args[i + 1]
            i += 2
            continue
        if a == "--namespace":
            out["namespace"] = args[i + 1]
            i += 2
            continue
        if a == "--json":
            out["json"] = True
        elif a in ("--dependency", "--triage-workload", "--evidence"):
            out["mode"] = a.lstrip("-")
            out["value"] = args[i + 1]
            i += 2
            continue
        elif a.startswith("--") and a not in ("--no-color", "--quiet"):
            out["mode"] = a.lstrip("-")
        i += 1
    return out


REPORTS = {
    "resources": [
        "SOURCE\tpods\tSTATUS\tOK\tUPDATED\t2026-10-03T00:00:00Z\tCACHE AGE\t0 sec",
        "POD\tREADY\tSTATUS\tRESTARTS\tAGE\tCPU USED\tCPU REQ\tCPU LIMIT\tMEM USED\t"
        "MEM REQ\tMEM LIMIT\tNODE\tIP\tOWNER\tCONTAINERS\tIMAGES",
        "transformer-abc\t1/1\tRunning\t0\t5d\tN/A\t100m\t1000m\tN/A\t64 MiB\t1 GiB\t"
        "node-1\t10.0.0.4\tDeployment/transformer\tmain\tregistry/transformer:6.4.0-10",
        "log-transformer-def\t0/1\tCrashLoopBackOff\t7\t2h\tN/A\t100m\t1000m\tN/A\t"
        "64 MiB\t1 GiB\tnode-2\t10.0.0.5\tDeployment/log-transformer\tmain\tregistry/log:1",
        "TOTALS (active pods; requests include init/sidecar peak and overhead)",
        "CPU USED\tINCOMPLETE [known=0]\tCPU REQUEST\t200m\tCPU LIMIT\t2000m",
    ],
    "triage": [
        "KUBERNETES TRIAGE | one-command incident scope",
        "CONTEXT\tvcluster-docker_dev",
        "NAMESPACE\tdevopsonm",
        "FINDINGS\tFAIL=1\tWARN=2\tUNKNOWN=0\tINFO=1 (full detail: --health)",
        "SEVERITY\tCATEGORY\tRESOURCE\tISSUE\tEVIDENCE\tNEXT CHECK",
        "FAIL\tPODS\tPod/log-transformer-def\tRunning pod is not Ready\t"
        "OBSERVED Pod Ready condition\tPod inspector + related events",
        "WARN\tRESTARTS\tPod/log-transformer-def/main\tRestart count 7\t"
        "OBSERVED cumulative count; not a restart rate\tPod inspector",
        "WARN\tEVENTS\tPod/log-transformer-def\tBackOff: Back-off restarting failed "
        "container\tOBSERVED retained event count=3 latest=2026-10-03T00:00:00Z\t"
        "Event timeline",
    ],
    "certificates": [
        "CERTIFICATES | namespace=devopsonm | TTL 60s | WARN <=30d CRITICAL <=7d",
        "TLS CERTIFICATE METADATA | OK | cache age=0s",
        "NAME\tCN\tISSUER\tNOT AFTER\tDAYS\tSTATUS\tCONSUMERS",
        "syslog-cert\tsyslog.local\tinternal-ca\t2026-11-01T00:00:00Z\t29\tWARN\t3",
        "transformer-tls\ttransformer.svc\tinternal-ca\t2027-06-01T00:00:00Z\t240\tOK\t1",
    ],
    "gitops": [
        "GITOPS / FLUX | context=vcluster-docker_dev namespace=flux-system",
        "gitrepositories | status=OK | cache age=0s",
        "TOTAL 2 | READY 1 | SUSPENDED 0 | FAILED 1",
        "",
        "GitRepository/devopsonm [FAIL RECONCILIATION_FAILED]",
        "  Ready=False suspend=false generation=1 observed=1",
        "  Artifact=main@sha1:7ac901b applied=- attempted=-",
        "  Reason=GitOperationFailed message=authentication required",
        "",
        "Kustomization/devopsonm [OK NO_DRIFT_EVIDENCE]",
        "  Ready=True suspend=false generation=1 observed=1",
        "  Source=GitRepository/devopsonm namespace=flux-system path=./clusters/dev",
        "  Artifact=- applied=main@sha1:7ac901b attempted=main@sha1:7ac901b",
        "  Reason=ReconciliationSucceeded message=Applied revision: main@sha1:7ac901b",
        "",
        "HelmRelease/transformer [WARN RECONCILIATION_PENDING]",
        "  Ready=Unknown suspend=false generation=2 observed=2",
        "  Reason=Progressing message=Reconciliation in progress",
    ],
    "network": [
        "SERVICE / NETWORK TOPOLOGY | namespace=devopsonm",
        "Service/transformer type=ClusterIP clusterIP=10.0.0.5 ports=8443:https",
        "\u251c\u2500\u2500 EndpointSlice: transformer-eps ready=2/2",
        "Service/syslog-svc type=ClusterIP clusterIP=10.0.0.6 ports=514:syslog",
        "NETWORK POLICIES",
    ],
    "storage": [
        "STORAGE DEPENDENCY GRAPH | namespace=devopsonm",
        "NAME\tSTATUS\tCAPACITY\tACCESS MODES\tSTORAGECLASS\tVOLUME",
        "data-0\tBound\t10Gi\tRWO\tstandard\tpv-0",
        "data-1\tPending\t10Gi\tRWO\tstandard\t-",
    ],
    "doctor": [
        " TOOLING",
        "kubectl                      AVAILABLE",
        "jq                           AVAILABLE",
        "openssl                      AVAILABLE",
        "helm                         AVAILABLE",
        "flux                         AVAILABLE",
        "psql                         NOT INSTALLED",
        "Metrics API                  OPTIONAL/UNAVAILABLE",
        "cert-manager CRDs            OPTIONAL/UNAVAILABLE",
    ],
    "capabilities": [
        "kubectl                      AVAILABLE",
        "jq                           AVAILABLE",
        "Metrics API                  OPTIONAL/UNAVAILABLE",
    ],
    "health": [
        "Context   %CONTEXT%",
        "Namespace %NAMESPACE%",
        "API       OK",
    ],
    "snapshot": [
        "Operations snapshot",
        "FAIL\tPODS\tPod/log-transformer-def\tRunning pod is not Ready",
    ],
    "dependency": [
        "Pod/transformer-abc -> ReplicaSet/transformer-xyz -> Deployment/transformer",
        "Service/transformer -> EndpointSlice/transformer-eps -> Pod/transformer-abc",
    ],
    "triage-workload": [
        "Workload Pod/log-transformer-def",
        "Warning BackOff 17:06 x7 Back-off restarting failed container",
        "ERROR certificate verify failed",
    ],
    "evidence": [
        "Evidence bundle created for %VALUE%",
    ],
    "gitops-graph": [
        "GitRepository/devopsonm -> Kustomization/devopsonm: NO_DRIFT_EVIDENCE (revision matches)",
        "Kustomization/devopsonm -> HelmRelease/transformer: NO_DRIFT_EVIDENCE",
    ],
    "etdp": ["Log Transformer -> TLS Secret -> CA Bundle -> Service"],
    "postgres-discovery": [
        "POSTGRESQL / GENERIC DB DISCOVERY | namespace=devopsonm",
        "SERVICE\tTYPE\tPORT\tCLUSTER IP\tEXTERNAL IP\tREADY ENDPOINT\tDATABASE\tUSERNAME",
        "pg-svc\tClusterIP\t5432\t10.0.0.9\t\t10.0.0.10\tUNKNOWN (safe metadata only)\t"
        "UNKNOWN (credential not read)",
        "stale-db\tClusterIP\t5432\t10.0.0.12\t\tUNKNOWN\tUNKNOWN (safe metadata only)\t"
        "UNKNOWN (credential not read)",
    ],
    "kafka-discovery": [
        "KAFKA DIAGNOSTICS DISCOVERY | namespace=devopsonm",
        "kafka-topics          : TOOL_MISSING",
        "kafka-consumer-groups : TOOL_MISSING",
        "",
        "SERVICE\tTYPE\tCLUSTER IP\tPORTS",
        "kafka\tClusterIP\t10.0.0.11\tkafka:9093",
    ],
}


def main() -> int:
    args = sys.argv[1:]
    opts = parse(args)
    if opts["mode"] == "sleep":
        time.sleep(30)
    lines = REPORTS.get(opts["mode"], ["No data"])
    lines = [
        line.replace("%CONTEXT%", opts["context"])
        .replace("%NAMESPACE%", opts["namespace"])
        .replace("%VALUE%", opts["value"])
        for line in lines
    ]
    # Deliberate secret to prove backend redaction works end to end.
    if opts["mode"] == "capabilities":
        lines.append("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret")
    exit_status = 1 if opts["mode"] == "triage" else 0
    if not opts["json"]:
        print("\n".join(lines))
        return exit_status
    payload = {
        "schema_version": "1.0",
        "application": "DevOpsSentinel",
        "tool_version": "4.2.2",
        "version": "4.2.2",
        "title": opts["mode"],
        "context": opts["context"],
        "namespace": opts["namespace"],
        "timestamp": "2026-10-03T00:00:00Z",
        "collected": "2026-10-03T00:00:00Z",
        "exit_status": exit_status,
        "lines": lines,
    }
    print(json.dumps(payload))
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
