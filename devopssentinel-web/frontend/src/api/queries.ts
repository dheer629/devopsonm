import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { isAutoConnectSuppressed, setAutoConnectSuppressed } from "@/lib/autoConnect";
import { del, getEnvelope, getOperation, postJson, type Scope } from "./client";
import type {
  BaselineComparison,
  BaselineSummary,
  Certificate,
  CertificateChain,
  DbServiceResource,
  Envelope,
  EventResource,
  FailurePath,
  Finding,
  GitOpsObject,
  GitOpsTimeline,
  Graph,
  HistoryItem,
  KafkaConsoleStatus,
  KafkaServiceResource,
  LogBundle,
  MountWarnings,
  NoteItem,
  OperationResponse,
  Pin,
  Pod,
  PodUsage,
  NodeUsage,
  PVCResource,
  QueryResultPayload,
  ResourceDescription,
  ReverseDependencies,
  SecretRecord,
  ServiceDns,
  ServiceResource,
  SqlConsoleStatus,
  SystemInfo,
  TopicListingPayload,
  Workload,
} from "@/types";

/** Query keys always encode scope so a context/namespace switch invalidates
 *  exactly the affected feature (spec section 9). */
export const keys = {
  system: () => ["system"] as const,
  contexts: () => ["contexts"] as const,
  namespaces: (context: string) => ["namespaces", context] as const,
  workloads: (s: Scope) => ["workloads", s.context ?? "", s.namespace ?? ""] as const,
  pods: (s: Scope) => ["pods", s.context ?? "", s.namespace ?? ""] as const,
  pod: (s: Scope, name: string) => ["pod", s.context ?? "", s.namespace ?? "", name] as const,
  findings: (s: Scope) => ["findings", s.context ?? "", s.namespace ?? ""] as const,
  events: (s: Scope) => ["events", s.context ?? "", s.namespace ?? ""] as const,
  gitops: (s: Scope) => ["gitops", s.context ?? "", s.namespace ?? ""] as const,
  certificates: (s: Scope) => ["certificates", s.context ?? "", s.namespace ?? ""] as const,
  services: (s: Scope) => ["services", s.context ?? "", s.namespace ?? ""] as const,
  storage: (s: Scope) => ["storage", s.context ?? "", s.namespace ?? ""] as const,
  graph: (s: Scope, kind: string, name: string) =>
    ["graph", s.context ?? "", s.namespace ?? "", kind, name] as const,
  doctor: (s: Scope) => ["doctor", s.context ?? "", s.namespace ?? ""] as const,
  capabilities: (s: Scope) => ["capabilities", s.context ?? "", s.namespace ?? ""] as const,
  applicationProfile: (s: Scope) =>
    ["application-profile", s.context ?? "", s.namespace ?? ""] as const,
  secrets: (s: Scope) => ["secrets", s.context ?? "", s.namespace ?? ""] as const,
  database: (s: Scope) => ["database", s.context ?? "", s.namespace ?? ""] as const,
  kafka: (s: Scope) => ["kafka", s.context ?? "", s.namespace ?? ""] as const,
  databaseServices: (s: Scope) =>
    ["database-services", s.context ?? "", s.namespace ?? ""] as const,
  kafkaServices: (s: Scope) => ["kafka-services", s.context ?? "", s.namespace ?? ""] as const,
  pins: () => ["pins"] as const,
  history: () => ["history"] as const,
  diagnostics: () => ["diagnostics"] as const,
  logs: (s: Scope, name: string) => ["logs", s.context ?? "", s.namespace ?? "", name] as const,
  logView: (s: Scope, params: Record<string, string | number | boolean>) =>
    ["log-view", s.context ?? "", s.namespace ?? "", JSON.stringify(params)] as const,
  containers: (s: Scope, pod: string) =>
    ["containers", s.context ?? "", s.namespace ?? "", pod] as const,
  describe: (s: Scope, kind: string, name: string, format: string) =>
    ["describe", s.context ?? "", s.namespace ?? "", kind, name, format] as const,
  snapshot: (s: Scope) => ["snapshot", s.context ?? "", s.namespace ?? ""] as const,
};

const STALE = 15_000;

function opQuery<T>(key: readonly unknown[], path: string, scope: Scope, extra = {}) {
  return {
    queryKey: key,
    queryFn: () => getOperation<T>(path, scope, extra),
    staleTime: STALE,
  };
}

export function useSystem() {
  return useQuery({
    queryKey: keys.system(),
    queryFn: () => getEnvelope<SystemInfo>("/api/v1/system"),
    staleTime: 60_000,
  });
}

export function useContexts() {
  return useQuery({
    queryKey: keys.contexts(),
    queryFn: () => getEnvelope<{ contexts: string[]; current: string }>("/api/v1/contexts"),
    staleTime: 30_000,
  });
}

export function useNamespaces(context: string) {
  return useQuery({
    queryKey: keys.namespaces(context),
    queryFn: () => getEnvelope<{ namespaces: string[] }>("/api/v1/namespaces", { context }),
    staleTime: 30_000,
    enabled: Boolean(context),
  });
}

export function useWorkloads(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Workload[]>>({
    ...opQuery<Workload[]>(keys.workloads(scope), "/api/v1/workloads", scope),
    enabled,
  });
}

export function usePods(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Pod[]>>({
    ...opQuery<Pod[]>(keys.pods(scope), "/api/v1/pods", scope),
    enabled,
  });
}

export function usePod(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.pod(scope, name), `/api/v1/pods/${name}`, scope),
    enabled: enabled && Boolean(name),
  });
}

export function usePodLogs(
  scope: Scope,
  name: string,
  extra: Record<string, string | number | boolean> = {},
) {
  return useQuery<OperationResponse<LogBundle>>({
    ...opQuery<LogBundle>(keys.logs(scope, name), `/api/v1/pods/${name}/logs`, scope, extra),
    enabled: Boolean(name),
  });
}

export function usePodEvents(scope: Scope, name: string) {
  return useQuery<OperationResponse<EventResource[]>>({
    ...opQuery<EventResource[]>(keys.events(scope), `/api/v1/pods/${name}/events`, scope),
    enabled: Boolean(name),
  });
}

export function useFindings(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Finding[]>>({
    ...opQuery<Finding[]>(keys.findings(scope), "/api/v1/findings", scope),
    enabled,
  });
}

export function useEvents(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<EventResource[]>>({
    ...opQuery<EventResource[]>(keys.events(scope), "/api/v1/events", scope),
    enabled,
  });
}

export interface ConnectionCandidate {
  id: string;
  source: string;
  label: string;
  kubeconfig: string;
  context: string;
  cluster: string;
  server: string;
  namespace: string;
  environment: string;
  inCluster: boolean;
}

export interface ActiveConnection {
  candidateId: string;
  kubeconfig: string;
  context: string;
  namespace: string;
  serverOverride: string;
  insecureSkipTlsVerify: boolean;
  environment: string;
  label: string;
  /** API server named by the kubeconfig itself, before any override. */
  server: string;
  effectiveKubeconfig: string;
  updatedAt: number;
}

export interface ConnectionList {
  files: { source: string; path: string; bytes: number }[];
  candidates: ConnectionCandidate[];
  active: ActiveConnection | null;
  /**
   * Whether the active connection is actually *usable*, not merely configured.
   * A vcluster's published port moves when it restarts, so a saved override can
   * go stale while the configuration still looks complete.
   */
  health: ConnectionHealth | null;
  kubectlAvailable: boolean;
  effectiveKubeconfig: string;
  stateDir: string;
  live: { sqlConsole: boolean; kafkaTopics: boolean };
}

export interface ConnectionHealth {
  configured: boolean;
  reachable: boolean;
  reason: string;
  detail: string;
  server: string;
  serverVersion: string;
  context: string;
  environment: string;
}

/** One endpoint/credential pairing attempt made by auto-connect. */
export interface AutoConnectAttempt {
  candidateId: string;
  context: string;
  kubeconfig: string;
  environment: string;
  server: string;
  serverOverride: string;
  endpointSource: string;
  endpointContainer: string;
  reachable: boolean;
  serverVersion: string;
  reason: string;
  detail: string;
}

export interface AutoConnectResult {
  activated: ActiveConnection | null;
  attempts: AutoConnectAttempt[];
  /** `ACTIVATED`, `ALREADY_CONNECTED`, `NO_KUBECONFIG`, or a failure reason. */
  reason: string;
  advice: string;
  serverOverride: string;
  detected: DiscoveredEndpoint | null;
  serverVersion: string;
  health: ConnectionHealth | null;
}

export interface ProbeResult {
  reachable: boolean;
  status: string;
  serverVersion: string;
  namespaceCount: number;
  latencyMs: number;
  detail: string;
}

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: () => getEnvelope<ConnectionList>("/api/v1/connections"),
    staleTime: 10_000,
  });
}

export function useProbeConnection() {
  return useMutation({
    mutationFn: (body: {
      candidateId?: string;
      kubeconfig?: string;
      context?: string;
      serverOverride?: string;
      insecureSkipTlsVerify?: boolean;
    }) => postJson<ProbeResult>("/api/v1/connections/probe", body),
  });
}

export function useActivateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      candidateId: string;
      namespace?: string;
      serverOverride?: string;
      insecureSkipTlsVerify?: boolean;
    }) => postJson<ActiveConnection>("/api/v1/connections/activate", body),
    // A new cluster changes every scope-dependent query.
    onSuccess: () => {
      // Asking for a connection clears an earlier explicit disconnect.
      setAutoConnectSuppressed(false);
      void queryClient.invalidateQueries();
    },
  });
}

export function useAutoDetectConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { force?: boolean } = {}) =>
      postJson<AutoConnectResult>("/api/v1/connections/auto", body),
    onSuccess: (envelope) => {
      // Reaching a cluster is the operator asking for one, whether they pressed
      // Connect or the page did it on load; either way a previous explicit
      // disconnect no longer applies.
      if (envelope.data.activated || envelope.data.reason === "ALREADY_CONNECTED") {
        setAutoConnectSuppressed(false);
      }
      void queryClient.invalidateQueries();
    },
  });
}

/**
 * Connect automatically when the console has no working cluster.
 *
 * Fires at most once per page load, and only when `/connections` reports the
 * current connection as missing or unreachable. That matters for three reasons:
 * a working connection is never replaced, an operator who disconnects mid-session
 * is not immediately reconnected behind their back, and an explicit Disconnect
 * is remembered across reloads until a connection is asked for again.
 *
 * The backend already auto-connects at startup, so this is the second line of
 * defence: it covers the case where the console came up before Docker or WSL
 * was ready, and it is what makes "open the page and the cluster is there" true
 * even after a cluster restart moves the published port.
 */
export function useAutoConnectOnLoad(needsConnection: boolean) {
  const autoDetect = useAutoDetectConnection();
  const attempted = useRef(false);
  const mutate = autoDetect.mutate;

  useEffect(() => {
    if (!needsConnection || attempted.current) return;
    // An explicit Disconnect is an instruction: do not undo it behind the
    // operator's back on the next load.
    if (isAutoConnectSuppressed()) return;
    attempted.current = true;
    mutate({});
  }, [needsConnection, mutate]);

  return autoDetect;
}

export function useDeactivateConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJson<{ active: null }>("/api/v1/connections/deactivate", {}),
    onSuccess: () => {
      // Remember the intent so the next page load does not reconnect.
      setAutoConnectSuppressed(true);
      void queryClient.invalidateQueries();
    },
  });
}

export interface DiscoveredEndpoint {
  server: string;
  source: string;
  container: string;
  kind: string;
  version: string;
  platform: string;
}

export interface DiscoveredContainer {
  name: string;
  image: string;
  state: string;
  status: string;
  kind: string;
  ports: number[];
}

export interface DiscoveryResult {
  dockerAvailable: boolean;
  docker: { mounted: boolean; usable: boolean; error: string };
  socket: string;
  containers: DiscoveredContainer[];
  endpoints: DiscoveredEndpoint[];
  probed: number;
}

export function useDiscoveredEndpoints(enabled = true) {
  return useQuery({
    queryKey: ["connections-discover"],
    queryFn: () => getEnvelope<DiscoveryResult>("/api/v1/connections/discover"),
    staleTime: 20_000,
    enabled,
  });
}

/** One kubeconfig's attempt to authenticate against a discovered endpoint. */
export interface PairAttempt {
  context: string;
  kubeconfig: string;
  environment: string;
  reachable: boolean;
  serverVersion: string;
  /** UNAUTHORIZED | FORBIDDEN | TLS | UNREACHABLE | TIMEOUT | INVALID | FAILED. */
  reason: string;
  detail: string;
}

export interface PairResult {
  activated: ActiveConnection | null;
  attempts: PairAttempt[];
  /** ACTIVATED | NO_KUBECONFIG | one of the PairAttempt reasons. */
  reason: string;
  /** Operator-facing next step when pairing failed. */
  advice: string;
}

export function usePairEndpoint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (server: string) =>
      postJson<PairResult>("/api/v1/connections/pair", { server }),
    onSuccess: (envelope) => {
      // Pairing is the operator asking for a connection, so an earlier explicit
      // disconnect no longer applies.
      if (envelope.data.activated) setAutoConnectSuppressed(false);
      void queryClient.invalidateQueries();
    },
  });
}

export function useLiveSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { sqlConsole?: boolean; kafkaTopics?: boolean }) =>
      postJson<{ sqlConsole: boolean; kafkaTopics: boolean }>("/api/v1/settings/live", body),
    onSuccess: () => void queryClient.invalidateQueries(),
  });
}

export function useGitOps(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<GitOpsObject[]>>({
    ...opQuery<GitOpsObject[]>(keys.gitops(scope), "/api/v1/gitops", scope),
    enabled,
  });
}

export function useCertificates(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Certificate[]>>({
    ...opQuery<Certificate[]>(keys.certificates(scope), "/api/v1/certificates", scope),
    enabled,
  });
}

export function useSecrets(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<SecretRecord[]>>({
    ...opQuery<SecretRecord[]>(keys.secrets(scope), "/api/v1/secrets", scope),
    enabled,
  });
}

// A type alias (not an interface) so it keeps an implicit index signature and
// can be handed straight to `getOperation`'s query-string builder.
export type LogViewParams = {
  pod: string;
  container?: string;
  tail?: number;
  since?: string;
  previous?: boolean;
  timestamps?: boolean;
};

/** One read-only `kubectl logs` with the log viewer's full option surface. */
export function useLogs(
  scope: Scope,
  params: LogViewParams,
  enabled = true,
  refetchInterval: number | false = false,
) {
  return useQuery<OperationResponse<LogBundle>>({
    queryKey: keys.logView(scope, params as unknown as Record<string, string | number | boolean>),
    queryFn: () => getOperation<LogBundle>("/api/v1/logs", scope, params),
    enabled: enabled && Boolean(params.pod),
    refetchInterval,
  });
}

/** Container names for one pod, so the log viewer can populate its picker. */
export function useContainers(scope: Scope, pod: string, enabled = true) {
  return useQuery<Envelope<{ pod: string; containers: string[] }>>({
    queryKey: keys.containers(scope, pod),
    queryFn: () =>
      getEnvelope<{ pod: string; containers: string[] }>("/api/v1/containers", scope, { pod }),
    enabled: enabled && Boolean(pod),
    staleTime: 30_000,
  });
}

export type DescribeParams = {
  kind: string;
  name: string;
  format: string;
};

/** Read-only describe / get -o yaml|json / events for one resource. */
export function useDescribe(scope: Scope, params: DescribeParams, enabled = true) {
  return useQuery<OperationResponse<ResourceDescription>>({
    queryKey: keys.describe(scope, params.kind, params.name, params.format),
    queryFn: () => getOperation<ResourceDescription>("/api/v1/describe", scope, params),
    enabled: enabled && Boolean(params.kind) && Boolean(params.name),
  });
}

export function useServices(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<ServiceResource[]>>({
    ...opQuery<ServiceResource[]>(keys.services(scope), "/api/v1/network/services", scope),
    enabled,
  });
}

export function useEndpointGaps(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<ServiceResource[]>>({
    ...opQuery<ServiceResource[]>(
      ["endpoint-gaps", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/network/endpoint-gaps",
      scope,
    ),
    enabled,
  });
}

export function useStorage(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<PVCResource[]>>({
    ...opQuery<PVCResource[]>(keys.storage(scope), "/api/v1/storage", scope),
    enabled,
  });
}

export function useGraph(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<OperationResponse<Graph>>({
    ...opQuery<Graph>(keys.graph(scope, kind, name), `/api/v1/graph/${kind}/${name}`, scope),
    enabled: enabled && Boolean(name),
  });
}

export function useGitOpsGraph(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Graph>>({
    ...opQuery<Graph>(
      ["gitops-graph", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/graph/gitops",
      scope,
    ),
    enabled,
  });
}

export function useImpact(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<
    OperationResponse<{ target: string; direct: string[]; graph: Graph; confidence?: string }>
  >({
    ...opQuery(
      ["impact", scope.context ?? "", scope.namespace ?? "", kind, name],
      `/api/v1/impact/${kind}/${name}`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function useDoctor(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.doctor(scope), "/api/v1/doctor", scope),
    enabled,
  });
}

export function useApplicationProfile(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.applicationProfile(scope), "/api/v1/application-profile", scope),
    enabled,
  });
}

export function useDatabase(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.database(scope), "/api/v1/database", scope),
    enabled,
  });
}

export function useKafka(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.kafka(scope), "/api/v1/kafka", scope),
    enabled,
  });
}

export function useDatabaseServices(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<DbServiceResource[]>>({
    ...opQuery<DbServiceResource[]>(
      keys.databaseServices(scope),
      "/api/v1/database/services",
      scope,
    ),
    enabled,
  });
}

export function useKafkaServices(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<KafkaServiceResource[]>>({
    ...opQuery<KafkaServiceResource[]>(
      keys.kafkaServices(scope),
      "/api/v1/kafka/services",
      scope,
    ),
    enabled,
  });
}

/** Opt-in live-data status probes (cheap, cached for a minute). */
export function useSqlConsole() {
  return useQuery<Envelope<SqlConsoleStatus>>({
    queryKey: ["sql-console"],
    queryFn: () => getEnvelope<SqlConsoleStatus>("/api/v1/database/console"),
    staleTime: 60_000,
  });
}

export function useKafkaConsole() {
  return useQuery<Envelope<KafkaConsoleStatus>>({
    queryKey: ["kafka-console"],
    queryFn: () => getEnvelope<KafkaConsoleStatus>("/api/v1/kafka/console"),
    staleTime: 60_000,
  });
}

export interface QueryRequestPayload {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  sql: string;
}

export function useRunQuery() {
  return useMutation<Envelope<QueryResultPayload>, Error, QueryRequestPayload>({
    mutationFn: (payload) => postJson<QueryResultPayload>("/api/v1/database/query", payload),
  });
}

export function useListTopics() {
  return useMutation<Envelope<TopicListingPayload>, Error, { host: string; port: number }>({
    mutationFn: (payload) => postJson<TopicListingPayload>("/api/v1/kafka/topics", payload),
  });
}

/** Observed resource usage (read-only `kubectl top`, refreshed on the live tick). */
/**
 * Node usage. `refetchIntervalMs` is how the usage charts observe: a metrics
 * read is instantaneous, so only repeated reads produce a trend. Leaving it
 * undefined keeps the query on the LIVE switch alone.
 */
export function useNodeMetrics(context: string, enabled = true, refetchIntervalMs?: number) {
  return useQuery<Envelope<{ nodes: NodeUsage[] }>>({
    queryKey: ["metrics-nodes", context],
    queryFn: () => getEnvelope<{ nodes: NodeUsage[] }>("/api/v1/metrics/nodes", { context }),
    enabled,
    staleTime: 5_000,
    refetchInterval: refetchIntervalMs,
  });
}

/** Pod usage, observed the same way as {@link useNodeMetrics}. */
export function usePodMetrics(scope: Scope, enabled = true, refetchIntervalMs?: number) {
  return useQuery<Envelope<{ pods: PodUsage[] }>>({
    queryKey: ["metrics-pods", scope.context ?? "", scope.namespace ?? ""],
    queryFn: () => getEnvelope<{ pods: PodUsage[] }>("/api/v1/metrics/pods", scope),
    enabled,
    staleTime: 5_000,
    refetchInterval: refetchIntervalMs,
  });
}

export function useSnapshot(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.snapshot(scope), "/api/v1/snapshot", scope),
    enabled,
  });
}

export function usePins() {
  return useQuery({
    queryKey: keys.pins(),
    queryFn: () => getEnvelope<Pin[]>("/api/v1/pins"),
  });
}

export function useHistory() {
  return useQuery({
    queryKey: keys.history(),
    queryFn: () => getEnvelope<HistoryItem[]>("/api/v1/history"),
  });
}

export function useDiagnostics(enabled: boolean) {
  return useQuery({
    queryKey: keys.diagnostics(),
    queryFn: () =>
      getEnvelope<{ cache: Record<string, number>; audit: Record<string, unknown>[] }>(
        "/api/v1/diagnostics",
      ),
    enabled,
    refetchInterval: enabled ? 5000 : false,
  });
}

export function useAddPin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pin: Omit<Pin, "pinnedAt">) => postJson<Pin[]>("/api/v1/pins", pin),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.pins() }),
  });
}

export function useRemovePin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => del<Pin[]>(`/api/v1/pins/${encodeURIComponent(id)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.pins() }),
  });
}

export function usePushHistory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (item: Partial<HistoryItem>) => postJson<HistoryItem[]>("/api/v1/history", item),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.history() }),
  });
}

/** One hit from the server-side global search. */
export interface SearchHit {
  kind: string;
  name: string;
  namespace: string;
  route: string;
  state: string;
  /** Engine provenance for this hit: LIVE | CACHE | UNAVAILABLE. */
  source: string;
  /** The engine operation that produced it, shown as source attribution. */
  engine: string;
}

export interface SearchResultSet {
  query: string;
  terms: string[];
  filters: Record<string, string>;
  results: SearchHit[];
  total: number;
  /** Domains the query actually covered. */
  searched: string[];
  /** Domains that could not be read, so a partial result is never silent. */
  unavailable: string[];
}

/**
 * Server-side global search (spec sections 11-12).
 *
 * The prefix grammar (`pod:`, `svc:`, `cert:`, `gitops:`, `pvc:`, `finding:`,
 * `ns:`, `status:`) is parsed by the backend, which queries the same engine
 * operations the domain pages use. Nothing is re-implemented in JavaScript.
 *
 * Below two characters nothing is sent, and previous results are kept while a
 * new query is in flight so the palette never flickers empty mid-typing.
 */
export function useResourceSearch(scope: Scope, query: string, enabled = true) {
  const q = query.trim();
  return useQuery({
    queryKey: ["search", scope.context ?? "", scope.namespace ?? "", q],
    queryFn: () => getEnvelope<SearchResultSet>("/api/v1/search", scope, { q }),
    enabled: enabled && q.length >= 2,
    staleTime: 15_000,
    retry: false,
    placeholderData: (previous) => previous,
  });
}

/* -------------------------------------------------------------------------
 * Deep-diagnostic hooks.
 *
 * These reach engine operations that were previously curl-only: the failure
 * path, blast radius, certificate chain and consumers, network port path and
 * DNS, storage consumers, and GitOps chains. Every one of them reads the same
 * engine report the domain page already uses -- no Kubernetes logic is added
 * here (spec sections 34-43, 66-86, 286, 290).
 * ---------------------------------------------------------------------- */

function detailKey(name: string, ...parts: string[]) {
  return (s: Scope) => [name, s.context ?? "", s.namespace ?? "", ...parts] as const;
}

/** The evidence-backed unhealthy chain through a resource (spec 40). */
export function useFailurePath(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<OperationResponse<FailurePath>>({
    ...opQuery<FailurePath>(
      detailKey("failure-path", kind, name)(scope),
      `/api/v1/failure-path/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(kind) && Boolean(name),
  });
}

/** Reverse dependencies: what consumes this object (spec 41). */
export function useConsumers(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<OperationResponse<ReverseDependencies>>({
    ...opQuery<ReverseDependencies>(
      detailKey("consumers", kind, name)(scope),
      `/api/v1/impact/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(kind) && Boolean(name),
  });
}

export function useCertificateDetail(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<{ certificate: Certificate | null; graph: Graph }>>({
    ...opQuery<{ certificate: Certificate | null; graph: Graph }>(
      detailKey("certificate", name)(scope),
      `/api/v1/certificates/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function useCertificateChain(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<CertificateChain>>({
    ...opQuery<CertificateChain>(
      detailKey("certificate-chain", name)(scope),
      `/api/v1/certificates/${encodeURIComponent(name)}/chain`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function useCertificateConsumers(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<ReverseDependencies>>({
    ...opQuery<ReverseDependencies>(
      detailKey("certificate-consumers", name)(scope),
      `/api/v1/certificates/${encodeURIComponent(name)}/consumers`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function useCertificateExpiry(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Certificate[]>>({
    ...opQuery<Certificate[]>(
      ["certificates-expiry", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/certificates/expiry",
      scope,
    ),
    enabled,
  });
}

export function useCertificateDuplicates(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Record<string, string[]>>>({
    ...opQuery<Record<string, string[]>>(
      ["certificates-duplicates", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/certificates/duplicates",
      scope,
    ),
    enabled,
  });
}

export function useCertificateIssuers(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string[]>>({
    ...opQuery<string[]>(
      ["certificates-issuers", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/certificates/issuers",
      scope,
    ),
    enabled,
  });
}

export function useEndpoints(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<ServiceResource[]>>({
    ...opQuery<ServiceResource[]>(
      ["network-endpoints", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/network/endpoints",
      scope,
    ),
    enabled,
  });
}

export function useServicePortPath(scope: Scope, service: string, enabled = true) {
  return useQuery<OperationResponse<{ service: ServiceResource | null; graph: Graph }>>({
    ...opQuery<{ service: ServiceResource | null; graph: Graph }>(
      detailKey("port-path", service)(scope),
      `/api/v1/network/port-path/${encodeURIComponent(service)}`,
      scope,
    ),
    enabled: enabled && Boolean(service),
  });
}

export function useServiceDns(scope: Scope, service: string, enabled = true) {
  return useQuery<OperationResponse<ServiceDns>>({
    ...opQuery<ServiceDns>(
      detailKey("service-dns", service)(scope),
      `/api/v1/network/dns/${encodeURIComponent(service)}`,
      scope,
    ),
    enabled: enabled && Boolean(service),
  });
}

export function usePodPolicies(scope: Scope, pod: string, enabled = true) {
  return useQuery<OperationResponse<ReverseDependencies>>({
    ...opQuery<ReverseDependencies>(
      detailKey("pod-policies", pod)(scope),
      `/api/v1/network/policies/${encodeURIComponent(pod)}`,
      scope,
    ),
    enabled: enabled && Boolean(pod),
  });
}

export function usePvcDetail(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<{ claim: PVCResource | null; graph: Graph }>>({
    ...opQuery<{ claim: PVCResource | null; graph: Graph }>(
      detailKey("pvc", name)(scope),
      `/api/v1/storage/pvc/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function usePvcConsumers(scope: Scope, name: string, enabled = true) {
  return useQuery<OperationResponse<ReverseDependencies>>({
    ...opQuery<ReverseDependencies>(
      detailKey("pvc-consumers", name)(scope),
      `/api/v1/storage/consumers/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(name),
  });
}

export function useMountWarnings(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<MountWarnings>>({
    ...opQuery<MountWarnings>(
      ["storage-mount-warnings", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/storage/mount-warnings",
      scope,
    ),
    enabled,
  });
}

export function useGitOpsDetail(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<OperationResponse<{ object: GitOpsObject | null; graph: Graph }>>({
    ...opQuery<{ object: GitOpsObject | null; graph: Graph }>(
      detailKey("gitops-detail", kind, name)(scope),
      `/api/v1/gitops/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`,
      scope,
    ),
    enabled: enabled && Boolean(kind) && Boolean(name),
  });
}

export function useGitOpsTimeline(scope: Scope, kind: string, name: string, enabled = true) {
  return useQuery<OperationResponse<GitOpsTimeline>>({
    ...opQuery<GitOpsTimeline>(
      detailKey("gitops-timeline", kind, name)(scope),
      `/api/v1/gitops/${encodeURIComponent(kind)}/${encodeURIComponent(name)}/timeline`,
      scope,
    ),
    enabled: enabled && Boolean(kind) && Boolean(name),
  });
}

export function useGitOpsChain(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<Graph>>({
    ...opQuery<Graph>(
      ["gitops-chain", scope.context ?? "", scope.namespace ?? ""],
      "/api/v1/gitops/chain",
      scope,
    ),
    enabled,
  });
}




export function useAddNote() {
  return useMutation({
    mutationFn: (payload: { incident_id: string; text: string }) =>
      postJson("/api/v1/notes", payload),
  });
}

export function useNotes(incidentId: string) {
  return useQuery({
    queryKey: ["notes", incidentId],
    queryFn: () => getEnvelope<NoteItem[]>(`/api/v1/notes/${incidentId}`),
    enabled: Boolean(incidentId),
  });
}

export function useBaselines() {
  return useQuery({
    queryKey: ["baselines"],
    queryFn: () => getEnvelope<BaselineSummary[]>("/api/v1/baselines"),
  });
}

export function useCaptureBaseline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; context?: string; namespace?: string }) =>
      postJson<BaselineSummary>("/api/v1/baselines", payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["baselines"] }),
  });
}

export function useCompareBaseline() {
  return useMutation({
    mutationFn: (payload: { name: string }) =>
      postJson<BaselineComparison>("/api/v1/baselines/compare", payload),
  });
}

export function useEvidenceIncidents() {
  return useQuery({
    queryKey: ["evidence"],
    queryFn: () =>
      getEnvelope<{ id: string; files: number; bytes: number; modified: number }[]>(
        "/api/v1/evidence",
      ),
  });
}

export function useEvidenceFiles(incidentId: string) {
  return useQuery({
    queryKey: ["evidence", incidentId],
    queryFn: () =>
      getEnvelope<{ path: string; bytes: number; modified: number }[]>(
        `/api/v1/evidence/${incidentId}`,
      ),
    enabled: Boolean(incidentId),
  });
}

export function useEvidenceFile(incidentId: string, path: string) {
  return useQuery({
    queryKey: ["evidence-file", incidentId, path],
    queryFn: () =>
      getEnvelope<{ path: string; content: string }>(
        `/api/v1/evidence/${incidentId}/file`,
        {},
        { path },
      ),
    enabled: Boolean(incidentId) && Boolean(path),
  });
}

export type { Envelope };

