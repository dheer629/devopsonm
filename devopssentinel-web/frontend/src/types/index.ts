/** Shared API types -- mirrors the backend envelope contract (schema 1.0). */

export type Source = "LIVE" | "CACHE" | "LOCAL" | "PARTIAL" | "UNAVAILABLE";

export interface Envelope<T> {
  schemaVersion: string;
  toolVersion: string;
  timestamp: string;
  context: string;
  namespace: string;
  source: Source;
  status: string;
  partial: boolean;
  durationMs: number;
  cacheAgeMs: number;
  data: T;
  warnings: string[];
  errors: string[];
}

export interface RawEvidence {
  engineArgv: string[];
  readOnlyCommand: string;
  exitStatus: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export interface OperationResponse<T> {
  envelope: Envelope<T>;
  raw?: RawEvidence;
  exitStatus?: number;
}

export interface Pod {
  name: string;
  namespace: string;
  phase: string;
  ready: string;
  restarts: number;
  node: string;
  age: string;
  ip: string;
  owner: string;
  status: string;
  containers: string[];
}

export interface Workload {
  name: string;
  kind: string;
  namespace: string;
  ready: string;
  status: string;
  restarts: number;
  node: string;
  age: string;
  cpu: string;
  memory: string;
  gitops: string;
}

export interface Finding {
  id: string;
  severity: string;
  lifecycle: string;
  domain: string;
  resource: string;
  finding: string;
  confidence: string;
  age: string;
  evidence: string;
}

export interface Certificate {
  name: string;
  namespace: string;
  cn: string;
  issuer: string;
  expiry: string;
  days: number | null;
  status: string;
  consumers: number;
  gitops: string;
}

export interface GitOpsObject {
  name: string;
  kind: string;
  namespace: string;
  ready: boolean | null;
  suspended: boolean;
  revision: string;
  applied_revision: string;
  message: string;
  status: string;
}

export interface ServiceResource {
  name: string;
  namespace: string;
  type: string;
  cluster_ip: string;
  external_ip: string;
  ready_endpoints: number;
  not_ready_endpoints: number;
  selector: string;
  ports: string;
  status: string;
}

export interface PVCResource {
  name: string;
  namespace: string;
  status: string;
  capacity: string;
  access_modes: string;
  storage_class: string;
  volume: string;
  severity: string;
  consumers: string[];
}

export interface DbServiceResource {
  name: string;
  namespace: string;
  type: string;
  port: string;
  cluster_ip: string;
  external_ip: string;
  ready_endpoint: string;
  database: string;
  username: string;
  status: string;
}

export interface KafkaServiceResource {
  name: string;
  namespace: string;
  type: string;
  cluster_ip: string;
  ports: string;
  bootstrap: string;
  status: string;
}

export interface SqlConsoleStatus {
  enabled: boolean;
  driverAvailable: boolean;
  maxRows: number;
  timeoutS: number;
  reason: string;
}

export interface QueryResultPayload {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  rowCount: number;
  truncated: boolean;
  target: string;
}

export interface KafkaConsoleStatus {
  enabled: boolean;
  timeoutS: number;
  reason: string;
}

export interface TopicInfo {
  name: string;
  partitions: number;
  internal: boolean;
}

export interface TopicListingPayload {
  bootstrap: string;
  brokers: string[];
  topics: TopicInfo[];
  truncated: boolean;
}

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  namespace: string;
  domain: string;
  state: string;
  confidence: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  confidence: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Capability {
  name: string;
  status: string;
  version: string;
  optional: boolean;
}

export interface EventResource {
  time: string;
  severity: string;
  reason: string;
  object: string;
  count: number;
  message: string;
}

export interface LogLine {
  n: number;
  text: string;
  level: string;
}

export interface LogBundle {
  pod: string;
  container: string;
  previous: boolean;
  lines: LogLine[];
  patterns: { pattern: string; count: number }[];
}

export interface OperationInfo {
  id: string;
  title: string;
  domain: string;
  mode: string;
  requires: string[];
  timeoutS: number;
}

export interface SystemInfo {
  webVersion: string;
  apiSchema: string;
  mode: string;
  readOnly: boolean;
  enginePath: string;
  engineAvailable: boolean;
  bashAvailable: boolean;
  kubeconfig: string;
  incidentId: string | null;
  debug: boolean;
  capabilities: Record<string, boolean>;
  operations: OperationInfo[];
  evidenceIncidents: number;
}

export interface NoteItem {
  id: string;
  text: string;
  author: string;
  at: number;
}

export interface BaselineSummary {
  name: string;
  context: string;
  namespace: string;
  capturedAt: number;
}

export type ComparisonResult =
  | "UNCHANGED"
  | "IMPROVED"
  | "DEGRADED"
  | "NEW"
  | "REMOVED"
  | "UNKNOWN";

export interface ComparisonRow {
  resource: string;
  pre: { status?: string | null; restarts?: number | null };
  post: { status?: string | null; restarts?: number | null };
  result: ComparisonResult;
}

export interface BaselineComparison {
  baseline: string;
  capturedAt: number;
  rows: ComparisonRow[];
}

export interface SearchResult {
  kind: string;
  name: string;
  namespace: string;
  route: string;
  state: string;
}

export interface Pin {
  id: string;
  kind: string;
  name: string;
  context: string;
  namespace: string;
  health: string;
  pinnedAt: number;
}

export interface HistoryItem {
  id: string;
  kind: string;
  name: string;
  context: string;
  namespace: string;
  visitedAt: number;
}
