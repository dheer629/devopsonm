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
    serial: "ABCDEF0123456789",
    fingerprint: "AA:BB:CC:DD",
    not_before: "2026-01-01",
    san: "DNS:syslog.local",
    source: "Secret/tls.crt certificate#1",
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
    serial: "0011223344556677",
    fingerprint: "11:22:33:44",
    not_before: "2026-01-01",
    san: "DNS:transformer.svc",
    source: "Secret/tls.crt certificate#1",
  },
];

export const SECRETS = [
  {
    name: "syslog-cert",
    namespace: "devopsonm",
    type: "kubernetes.io/tls",
    created: "2026-01-01T00:00:00Z",
    key_count: 2,
    keys: "tls.crt tls.key",
    is_tls: true,
    expires: "2026-11-01",
    days: 29,
    status: "WARNING",
  },
  {
    name: "transformer-tls",
    namespace: "devopsonm",
    type: "kubernetes.io/tls",
    created: "2026-01-01T00:00:00Z",
    key_count: 2,
    keys: "tls.crt tls.key",
    is_tls: true,
    expires: "2027-06-01",
    days: 240,
    status: "OK",
  },
  {
    name: "transformer-db",
    namespace: "devopsonm",
    type: "Opaque",
    created: "2026-01-01T00:00:00Z",
    key_count: 1,
    keys: "dsn",
    is_tls: false,
    expires: "",
    days: null,
    status: "INFO",
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

/** `/connections` — the Settings page reads `active` and `health` from here. */
export const CONNECTIONS = {
  files: [{ source: "host-kube", path: "/host-kube/config", bytes: 4187 }],
  candidates: [],
  active: {
    candidateId: "vcluster-docker_dev",
    kubeconfig: "/host-kube/config",
    context: "vcluster-docker_dev",
    namespace: "devopsonm",
    serverOverride: "https://host.docker.internal:11259",
    insecureSkipTlsVerify: true,
    environment: "vcluster",
    label: "vcluster-docker_dev",
    server: "https://127.0.0.1:11259",
    effectiveKubeconfig: "/state/kubeconfig",
    updatedAt: 1_760_000_000_000,
  },
  health: {
    configured: true,
    reachable: true,
    reason: "",
    detail: "",
    server: "https://host.docker.internal:11259",
    serverVersion: "v1.30.4",
    context: "vcluster-docker_dev",
    environment: "vcluster",
  },
  kubectlAvailable: true,
  effectiveKubeconfig: "/state/kubeconfig",
  stateDir: "/state",
  live: { sqlConsole: false, kafkaTopics: false },
};

/** `/storage/mount-warnings` — nothing mounted twice, nothing left unconsumed. */
export const MOUNT_WARNINGS = { warnings: [], unconsumed: [] };

/** The index the server-side search answers from (`/search?q=`). */
export const SEARCH_INDEX = [
  { kind: "Pod", name: "transformer-abc", namespace: "devopsonm", route: "/workloads", state: "OK" },
  { kind: "Service", name: "transformer", namespace: "devopsonm", route: "/network", state: "OK" },
  { kind: "Certificate", name: "transformer-tls", namespace: "devopsonm", route: "/pki", state: "OK" },
  { kind: "PVC", name: "data-1", namespace: "devopsonm", route: "/storage", state: "WARNING" },
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
    // Metrics are the one read whose *history* the UI builds from repeated
    // samples, so these two routes stamp each response the way the real
    // endpoint does. A frozen timestamp would make the charts look incapable of
    // accumulating, which is exactly the behaviour under test.
    if (path.endsWith("/metrics/nodes")) {
      return json(
        envelope({ nodes: NODE_USAGE }, { source: "LIVE", timestamp: new Date().toISOString() }),
      );
    }
    if (path.endsWith("/metrics/pods")) {
      return json(
        envelope({ pods: POD_USAGE }, { source: "LIVE", timestamp: new Date().toISOString() }),
      );
    }
    if (path.endsWith("/pods")) return json({ envelope: envelope(PODS), raw: rawEvidence() });
    if (path.endsWith("/workloads")) return json({ envelope: envelope(WORKLOADS), raw: rawEvidence() });
    if (path.endsWith("/findings")) return json({ envelope: envelope(FINDINGS), raw: rawEvidence() });
    if (path.endsWith("/events")) return json({ envelope: envelope([]), raw: rawEvidence() });
    if (path.endsWith("/certificates")) {
      return json({ envelope: envelope(CERTIFICATES), raw: rawEvidence() });
    }
    if (path.endsWith("/secrets")) {
      return json({ envelope: envelope(SECRETS), raw: rawEvidence() });
    }
    // The PKI page reads three deeper certificate views on load (spec 34-43).
    if (path.endsWith("/certificates/expiry")) {
      return json({ envelope: envelope(CERTIFICATES), raw: rawEvidence() });
    }
    if (path.endsWith("/certificates/duplicates")) {
      return json({ envelope: envelope({}), raw: rawEvidence() });
    }
    if (path.endsWith("/certificates/issuers")) {
      return json({ envelope: envelope(["internal-ca"]), raw: rawEvidence() });
    }
    if (path.endsWith("/gitops")) return json({ envelope: envelope(GITOPS), raw: rawEvidence() });
    if (path.endsWith("/network/services")) {
      return json({ envelope: envelope(SERVICES), raw: rawEvidence() });
    }
    if (path.endsWith("/network/endpoint-gaps")) {
      return json({ envelope: envelope([SERVICES[1]]), raw: rawEvidence() });
    }
    if (path.endsWith("/storage")) return json({ envelope: envelope(PVCS), raw: rawEvidence() });
    if (path.endsWith("/storage/mount-warnings")) {
      return json({ envelope: envelope(MOUNT_WARNINGS), raw: rawEvidence() });
    }
    if (path.endsWith("/network/endpoints")) {
      return json({ envelope: envelope(SERVICES), raw: rawEvidence() });
    }
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
    if (path.endsWith("/application-profile")) {
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
            reason:
              "disabled: turn on the Read-only SQL console switch in Settings (it applies immediately, no restart needed)",
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
            reason:
              "disabled: turn on the Kafka topic listing switch in Settings (it applies immediately, no restart needed)",
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
    // Pod-detail logs (engine-derived, PARTIAL) must win over the /logs viewer.
    if (path.includes("/pods/") && path.endsWith("/logs")) {
      return json({
        envelope: envelope(
          {
            pod: "log-transformer-def",
            container: "",
            previous: false,
            lines: [
              { n: 1, text: "ERROR certificate verify failed", level: "ERROR", ts: "" },
              { n: 2, text: "INFO retrying", level: "INFO", ts: "" },
            ],
            patterns: [{ pattern: "ERROR certificate verify failed", count: 2 }],
            since: "",
            tail: 500,
            timestamps: false,
            containers: [],
          },
          { source: "PARTIAL", status: "PARTIAL", partial: true, warnings: ["CLI-only"] },
        ),
        raw: rawEvidence(),
      });
    }
    if (path.endsWith("/logs")) {
      return json({
        envelope: envelope(
          {
            pod: "log-transformer-def",
            container: "main",
            previous: false,
            lines: [
              {
                n: 1,
                text: "ERROR certificate verify failed",
                level: "ERROR",
                ts: "2026-10-03T00:00:02Z",
              },
              { n: 2, text: "INFO retrying", level: "INFO", ts: "2026-10-03T00:00:03Z" },
            ],
            patterns: [{ pattern: "ERROR certificate verify failed", count: 2 }],
            since: "15m",
            tail: 500,
            timestamps: true,
            containers: ["main", "sidecar"],
          },
          { source: "LIVE", status: "OK" },
        ),
        raw: rawEvidence(),
      });
    }
    if (path.endsWith("/containers")) {
      return json(
        envelope({ pod: "log-transformer-def", containers: ["main", "sidecar"] }, { source: "LIVE" }),
      );
    }
    if (path.endsWith("/describe")) {
      return json({
        envelope: envelope(
          {
            kind: url.searchParams.get("kind") ?? "Pod",
            name: url.searchParams.get("name") ?? "log-transformer-def",
            namespace: "devopsonm",
            format: url.searchParams.get("format") ?? "describe",
            content: "Name: log-transformer-def\nNamespace: devopsonm\nStatus: Running",
            events: [],
          },
          { source: "LIVE", status: "OK" },
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
    if (path.endsWith("/connections")) {
      return json(envelope(CONNECTIONS, { source: "LOCAL" }));
    }
    if (path.endsWith("/settings/live")) {
      return json(envelope({ sqlConsole: false, kafkaTopics: false }, { source: "LOCAL" }));
    }
    if (path.endsWith("/search")) {
      // The palette asks the server; answer from the same index the pages render.
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const term = q.replace(/^\w+:/, "");
      const results = SEARCH_INDEX.filter((hit) =>
        hit.name.toLowerCase().includes(term),
      ).map((hit) => ({ ...hit, source: "LIVE", engine: "fixture" }));
      return json(
        envelope(
          {
            query: q,
            terms: q ? [q] : [],
            filters: {},
            results,
            total: results.length,
            searched: ["Pod", "Service", "Certificate", "PVC"],
            unavailable: [],
          },
          { source: "LIVE" },
        ),
      );
    }
    // An unmocked route is a gap in *this fixture*, not a response the real
    // backend would ever send. Returning an empty envelope here handed pages a
    // shape they read one level too deep, which blanked whole views behind the
    // ErrorBoundary; a 404 names the gap in the test that hits it.
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `no fixture for ${path}` }),
    });
  });
}

