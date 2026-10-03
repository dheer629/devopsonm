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
        "NAME                 READY   STATUS             RESTARTS   NODE      AGE",
        "transformer-abc      1/1     Running            0          node-1    5d",
        "log-transformer-def  0/1     CrashLoopBackOff   7          node-2    2h",
    ],
    "triage": [
        "CRITICAL  Pod/log-transformer-def  CrashLoopBackOff  exit code 1",
        "WARNING   Certificate/syslog-cert  29 days remaining",
        "OK        Deployment/transformer   Ready 2/2",
    ],
    "certificates": [
        "NAME           NAMESPACE   CN               ISSUER        EXPIRY      DAYS   CONSUMERS",
        "syslog-cert    etdp        syslog.local     internal-ca   2026-11-01  29     3",
        "transformer-tls etdp       transformer.svc  internal-ca   2027-06-01  240    1",
    ],
    "gitops": [
        "NAME          READY   REVISION           APPLIED            KIND",
        "devopsonm     True    main@sha1:7ac901b  main@sha1:7ac901b  Kustomization",
        "transformer   False   main@sha1:7ac901b  main@sha1:7ac901a  HelmRelease",
    ],
    "network": [
        "NAME         TYPE        CLUSTERIP   READY   PORTS",
        "transformer  ClusterIP   10.0.0.5    2      8443/TCP",
        "syslog-svc   ClusterIP   10.0.0.6    0      514/UDP",
    ],
    "storage": [
        "NAME         STATUS   CAPACITY   STORAGECLASS",
        "data-0       Bound    10Gi       standard",
        "data-1       Pending  10Gi       standard",
    ],
    "doctor": [
        "kubectl              AVAILABLE    v1.29.0",
        "jq                   AVAILABLE    1.7",
        "openssl              AVAILABLE    3.0.13",
        "flux                 AVAILABLE    2.4.0",
        "helm                 AVAILABLE    3.15.0",
        "Metrics API          UNAVAILABLE  OPTIONAL",
        "cert-manager         AVAILABLE    v1.15.0",
    ],
    "capabilities": [
        "kubectl              AVAILABLE",
        "jq                   AVAILABLE",
        "Metrics API          UNAVAILABLE",
    ],
    "health": [
        "Context   %CONTEXT%",
        "Namespace %NAMESPACE%",
        "API       OK",
    ],
    "snapshot": [
        "Operations snapshot",
        "CRITICAL Pod/log-transformer-def CrashLoopBackOff",
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
        "GitRepository/devopsonm -> Kustomization/devopsonm -> HelmRelease/transformer",
        "HelmRelease/transformer -> Deployment/transformer",
    ],
    "etdp": ["Log Transformer -> TLS Secret -> CA Bundle -> Service"],
    "postgres-discovery": ["Service pg-svc ClusterIP 10.0.0.9 5432 ready"],
    "kafka-discovery": ["Bootstrap kafka:9093 TLS=true"],
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
