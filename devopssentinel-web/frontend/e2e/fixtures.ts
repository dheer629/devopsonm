import type { Page } from "@playwright/test";

/** Deterministic API fixtures so the browser suite needs no cluster. */

export function envelope<T>(data: T, overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: "1.0",
    toolVersion: "4.2.2",
    timestamp: "2026-10-03T00:00:00Z",
    context: "vcluster-docker_dev",
    namespace: "devopsonm",
    source: "LIVE",
    status: "OK",
    partial: false,
    durationMs: 742,
    cacheAgeMs: 0,
    data,
    warnings: [],
    errors: [],
    ...overrides,
  };
}

export function rawEvidence() {
  return {
    engineArgv: ["bash", "DevOps_K8s_Sentinel_FINAL_GP.sh", "--no-color", "--resources", "--json"],
    readOnlyCommand: "bash DevOps_K8s_Sentinel_FINAL_GP.sh --no-color --resources --json",
    exitStatus: 0,
    stdout: '{"lines":[]}',
    stderr: "",
    durationMs: 742,
  };
}

export const PODS = [
  {
    name: "transformer-abc",
    namespace: "devopsonm",
    phase: "Running",
    ready: "1/1",
    restarts: 0,
    node: "node-1",
    age: "5d",
    ip: "10.0.0.4",
    owner: "Deployment/transformer",
    status: "OK",
    containers: [],
  },
  {
    name: "log-transformer-def",
    namespace: "devopsonm",
    phase: "CrashLoopBackOff",
    ready: "0/1",
    restarts: 7,
    node: "node-2",
    age: "2h",
    ip: "10.0.0.5",
    owner: "Deployment/log-transformer",
    status: "CRITICAL",
    containers: [],
  },
];

export const WORKLOADS = [
  {
    name: "transformer",
    kind: "Deployment",
    namespace: "devopsonm",
    ready: "2/2",
    status: "OK",
    restarts: 0,
    node: "",
    age: "5d",
    cpu: "12m",
    memory: "84Mi",
    gitops: "HelmRelease/transformer",
  },
  {
    name: "log-transformer",
    kind: "Deployment",
    namespace: "devopsonm",
    ready: "0/1",
    status: "CRITICAL",
    restarts: 7,
    node: "",
    age: "2h",
    cpu: "3m",
    memory: "40Mi",
    gitops: "HelmRelease/log-transformer",
  },
];

export const FINDINGS = [
  {
    id: "F-001",
    severity: "CRITICAL",
    lifecycle: "ACTIVE",
    domain: "Workload",
    resource: "Pod/log-transformer-def",
    finding: "CRITICAL Pod/log-transformer-def CrashLoopBackOff exit code 1",
    confidence: "CONFIRMED",
    age: "",
    evidence: "previous exit code 1",
  },
  {
    id: "F-002",
    severity: "WARNING",
    lifecycle: "ACTIVE",
    domain: "PKI",
    resource: "Secret/syslog-cert",
    finding: "WARNING Certificate/syslog-cert 29 days remaining",
    confidence: "CONFIRMED",
    age: "",
    evidence: "notAfter",
  },
];

export const CERTIFICATES = [
  {
    name: "syslog-cert",
    namespace: "devopsonm",
    cn: "syslog.local",
    issuer: "internal-ca",
    expiry: "2026-11-01",
    days: 29,
    status: "WARNING",
    consumers: 3,
    gitops: "",
  },
  {
    name: "transformer-tls",
    namespace: "devopsonm",
    cn: "transformer.svc",
    issuer: "internal-ca",
    expiry: "2027-06-01",
    days: 240,
    status: "OK",
    consumers: 1,
    gitops: "",
  },
];

export const GITOPS = [
  {
    name: "devopsonm",
    kind: "Kustomization",
    namespace: "flux-system",
    ready: true,
    suspended: false,
    revision: "main@sha1:7ac901b",
    applied_revision: "main@sha1:7ac901b",
    message: "",
    status: "OK",
  },
  {
    name: "transformer",
    kind: "HelmRelease",
    namespace: "flux-system",
    ready: false,
    suspended: false,
    revision: "main@sha1:7ac901b",
    applied_revision: "main@sha1:7ac901a",
    message: "reconcile failed",
    status: "FAILED",
  },
];

export const SERVICES = [
  {
    name: "transformer",
    namespace: "devopsonm",
    type: "ClusterIP",
    cluster_ip: "10.0.0.5",
    external_ip: "",
    ready_endpoints: 2,
    not_ready_endpoints: 0,
    selector: "app=transformer",
    ports: "8443/TCP",
    status: "OK",
  },
  {
    name: "syslog-svc",
    namespace: "devopsonm",
    type: "ClusterIP",
    cluster_ip: "10.0.0.6",
    external_ip: "",
    ready_endpoints: 0,
    not_ready_endpoints: 0,
    selector: "app=syslog",
    ports: "514/UDP",
    status: "WARNING",
  },
];

export const PVCS = [
  {
    name: "data-0",
    namespace: "devopsonm",
    status: "Bound",
    capacity: "10Gi",
    access_modes: "RWO",
    storage_class: "standard",
    volume: "pv-0",
    consumers: ["transformer-abc"],
    severity: "OK",
  },
  {
    name: "data-1",
    namespace: "devopsonm",
    status: "Pending",
    capacity: "10Gi",
    access_modes: "RWO",
    storage_class: "standard",
    volume: "",
    consumers: [],
    severity: "WARNING",
  },
];

export const DB_SERVICES = [
  {
    name: "pg-svc",
    namespace: "devopsonm",
    type: "ClusterIP",
    port: "5432",
    cluster_ip: "10.0.0.9",
    external_ip: "",
    ready_endpoint: "10.0.0.4",
    database: "UNKNOWN (safe metadata only)",
    username: "UNKNOWN (credential not read)",
    status: "OK",
  },
  {
    name: "stale-db",
    namespace: "devopsonm",
    type: "ClusterIP",
    port: "5432",
    cluster_ip: "10.0.0.12",
    external_ip: "",
    ready_endpoint: "UNKNOWN",
    database: "UNKNOWN (safe metadata only)",
    username: "UNKNOWN (credential not read)",
    status: "WARNING",
  },
];

export const KAFKA_SERVICES = [
  {
    name: "kafka",
    namespace: "devopsonm",
    type: "ClusterIP",
    cluster_ip: "10.0.0.11",
    ports: "kafka:9093",
    bootstrap: "kafka.devopsonm.svc:9093",
    status: "OK",
  },
];

export const NODE_USAGE = [
  {
    name: "minikube",
    cpuMillicores: 140,
    cpuCores: 0.14,
    cpuPercent: 0,
    memoryBytes: 1850 * 1024 * 1024,
    memoryPercent: 24,
  },
];

export const POD_USAGE = [
  {
    name: "log-transformer-def",
    cpuMillicores: 15,
    cpuCores: 0.015,
    memoryBytes: 58 * 1024 * 1024,
  },
  {
    name: "transformer-abc",
    cpuMillicores: 1,
    cpuCores: 0.001,
    memoryBytes: 19 * 1024 * 1024,
  },
];

export const GRAPH = {
  nodes: [
    { id: "Pod/transformer-abc", kind: "Pod", name: "transformer-abc", namespace: "devopsonm", domain: "kubernetes", state: "OK", confidence: "CONFIRMED" },
    { id: "ReplicaSet/transformer-xyz", kind: "ReplicaSet", name: "transformer-xyz", namespace: "devopsonm", domain: "kubernetes", state: "OK", confidence: "CONFIRMED" },
    { id: "Deployment/transformer", kind: "Deployment", name: "transformer", namespace: "devopsonm", domain: "kubernetes", state: "OK", confidence: "CONFIRMED" },
  ],
  edges: [
    { id: "a", source: "Pod/transformer-abc", target: "ReplicaSet/transformer-xyz", label: "OWNS", confidence: "CONFIRMED" },
    { id: "b", source: "ReplicaSet/transformer-xyz", target: "Deployment/transformer", label: "OWNS", confidence: "CONFIRMED" },
  ],
};

export const SYSTEM = {
  webVersion: "1.0.0",
  apiSchema: "1.0",
  mode: "SUPERVISION [READ ONLY]",
  readOnly: true,
  enginePath: "/workspace/DevOps_K8s_Sentinel_FINAL_GP.sh",
  engineAvailable: true,
  bashAvailable: true,
  kubeconfig: "/home/user/.kube/config",
  nodeAddress: "10.0.0.7",
  incidentId: null,
  debug: false,
  capabilities: { kubectl: true, jq: true, flux: true, helm: true, openssl: true, psql: false, kafka: false },
  operations: [],
  evidenceIncidents: 0,
};

export async function installFixtures(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

    if (path.endsWith("/system")) return json(envelope(SYSTEM, { source: "LOCAL" }));
    if (path.endsWith("/contexts")) {
      return json(
        envelope(
          { contexts: ["vcluster-docker_dev"], current: "vcluster-docker_dev" },
          { source: "LOCAL" },
        ),
      );
    }
    if (path.endsWith("/namespaces")) {
      return json(envelope({ namespaces: ["devopsonm", "flux-system"] }, { source: "LOCAL" }));
    }
    // Usage routes must be matched before the generic "/pods" rule below.
    if (path.endsWith("/metrics/nodes")) {
      return json(envelope({ nodes: NODE_USAGE }, { source: "LIVE" }));
    }
    if (path.endsWith("/metrics/pods")) {
      return json(envelope({ pods: POD_USAGE }, { source: "LIVE" }));
    }
    if (path.endsWith("/pods")) return json({ envelope: envelope(PODS), raw: rawEvidence() });
    if (path.endsWith("/workloads")) return json({ envelope: envelope(WORKLOADS), raw: rawEvidence() });
    if (path.endsWith("/findings")) return json({ envelope: envelope(FINDINGS), raw: rawEvidence() });
    if (path.endsWith("/events")) return json({ envelope: envelope([]), raw: rawEvidence() });
    if (path.endsWith("/certificates")) {
      return json({ envelope: envelope(CERTIFICATES), raw: rawEvidence() });
    }
    if (path.endsWith("/gitops")) return json({ envelope: envelope(GITOPS), raw: rawEvidence() });
    if (path.endsWith("/network/services")) {
      return json({ envelope: envelope(SERVICES), raw: rawEvidence() });
    }
    if (path.endsWith("/network/endpoint-gaps")) {
      return json({ envelope: envelope([SERVICES[1]]), raw: rawEvidence() });
    }
    if (path.endsWith("/storage")) return json({ envelope: envelope(PVCS), raw: rawEvidence() });
    // Graph routes must be matched before the generic "/gitops" rule.
    if (path.endsWith("/graph/gitops")) {
      return json({ envelope: envelope(GRAPH), raw: rawEvidence() });
    }
    if (path.includes("/graph/")) return json({ envelope: envelope(GRAPH), raw: rawEvidence() });
    if (path.includes("/impact/")) {
      return json({
        envelope: envelope({
          target: "Pod/transformer-abc",
          direct: ["Service/transformer"],
          graph: GRAPH,
          confidence: "HIGH CONFIDENCE",
        }),
        raw: rawEvidence(),
      });
    }
    if (path.endsWith("/doctor")) {
      return json({
        envelope: envelope("kubectl  AVAILABLE  v1.29.0\njq  AVAILABLE  1.7"),
        raw: rawEvidence(),
      });
    }
    if (path.endsWith("/etdp")) {
      return json({
        envelope: envelope("Log Transformer -> TLS Secret -> Service"),
        raw: rawEvidence(),
      });
    }
    if (path.endsWith("/database/console")) {
      return json(
        envelope(
          {
            enabled: false,
            driverAvailable: false,
            maxRows: 200,
            timeoutS: 15,
            defaultHost: "10.0.0.7",
            reason: "disabled: start the backend with DSWEB_ENABLE_SQL_CONSOLE=1",
          },
          { source: "LOCAL" },
        ),
      );
    }
    if (path.endsWith("/kafka/console")) {
      return json(
        envelope(
          {
            enabled: false,
            timeoutS: 8,
            defaultHost: "10.0.0.7",
            reason: "disabled: start the backend with DSWEB_ENABLE_KAFKA_TOPICS=1",
          },
          { source: "LOCAL" },
        ),
      );
    }
    if (path.endsWith("/database/services")) {
      return json({ envelope: envelope(DB_SERVICES), raw: rawEvidence() });
    }
    if (path.endsWith("/database")) {
      return json({ envelope: envelope("pg-svc ClusterIP 5432 ready"), raw: rawEvidence() });
    }
    if (path.endsWith("/kafka/services")) {
      return json({ envelope: envelope(KAFKA_SERVICES), raw: rawEvidence() });
    }
    if (path.endsWith("/kafka")) {
      return json({ envelope: envelope("kafka:9093 TLS=true"), raw: rawEvidence() });
    }
    if (path.endsWith("/pins")) return json(envelope([], { source: "LOCAL" }));
    if (path.endsWith("/history")) return json(envelope([], { source: "LOCAL" }));
    if (path.includes("/baselines/compare")) {
      return json(
        envelope(
          {
            baseline: "pre-change",
            capturedAt: 1_790_000_000,
            rows: [
              {
                resource: "transformer",
                pre: { status: "OK", restarts: 0 },
                post: { status: "OK", restarts: 0 },
                result: "UNCHANGED",
              },
              {
                resource: "log-transformer",
                pre: { status: "OK", restarts: 0 },
                post: { status: "CRITICAL", restarts: 7 },
                result: "DEGRADED",
              },
            ],
          },
          { source: "LOCAL" },
        ),
      );
    }
    if (path.includes("/baselines")) {
      return json(
        envelope(
          [{ name: "pre-change", context: "vcluster-docker_dev", namespace: "devopsonm", capturedAt: 1_790_000_000 }],
          { source: "LOCAL" },
        ),
      );
    }
    if (path.includes("/notes")) {
      return json(
        envelope(
          [{ id: "n1", text: "checked pods after rollout", author: "operator", at: 1_790_000_000 }],
          { source: "LOCAL" },
        ),
      );
    }
    if (path.includes("/evidence/")) return json(envelope([], { source: "LOCAL" }));
    if (path.endsWith("/evidence")) return json(envelope([], { source: "LOCAL" }));
    if (path.endsWith("/diagnostics")) {
      return json(envelope({ cache: { entries: 3, hits: 5, misses: 2 }, audit: [] }, { source: "LOCAL" }));
    }
    if (path.includes("/logs")) {
      return json({
        envelope: envelope(
          {
            pod: "log-transformer-def",
            container: "",
            previous: false,
            lines: [
              { n: 1, text: "ERROR certificate verify failed", level: "ERROR" },
              { n: 2, text: "INFO retrying", level: "INFO" },
            ],
            patterns: [{ pattern: "ERROR certificate verify failed", count: 2 }],
          },
          { source: "PARTIAL", status: "PARTIAL", partial: true, warnings: ["CLI-only"] },
        ),
        raw: rawEvidence(),
      });
    }
    if (path.includes("/pods/")) {
      return json({
        envelope: envelope("Pod report\nWarning BackOff 17:06 x7"),
        raw: rawEvidence(),
      });
    }
    return json(envelope(null));
  });
}

