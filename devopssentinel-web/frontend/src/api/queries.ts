import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, getEnvelope, getOperation, postJson, type Scope } from "./client";
import type {
  Certificate,
  Envelope,
  EventResource,
  Finding,
  GitOpsObject,
  Graph,
  HistoryItem,
  LogBundle,
  OperationResponse,
  Pin,
  Pod,
  PVCResource,
  ServiceResource,
  SystemInfo,
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
  etdp: (s: Scope) => ["etdp", s.context ?? "", s.namespace ?? ""] as const,
  database: (s: Scope) => ["database", s.context ?? "", s.namespace ?? ""] as const,
  kafka: (s: Scope) => ["kafka", s.context ?? "", s.namespace ?? ""] as const,
  pins: () => ["pins"] as const,
  history: () => ["history"] as const,
  diagnostics: () => ["diagnostics"] as const,
  logs: (s: Scope, name: string) => ["logs", s.context ?? "", s.namespace ?? "", name] as const,
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

export function useEtDp(scope: Scope, enabled = true) {
  return useQuery<OperationResponse<string>>({
    ...opQuery<string>(keys.etdp(scope), "/api/v1/etdp", scope),
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

export function useAddNote() {
  return useMutation({
    mutationFn: (payload: { incident_id: string; text: string }) =>
      postJson("/api/v1/notes", payload),
  });
}

export type { Envelope };

