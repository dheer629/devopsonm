import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Waypoints } from "lucide-react";

import {
  useCertificates,
  useConsumers,
  useFailurePath,
  useGitOps,
  useGitOpsGraph,
  useGraph,
  usePods,
  useServices,
  useWorkloads,
} from "@/api/queries";
import {
  ConfidenceTag,
  EmptyState,
  ErrorState,
  Field,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
} from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SEVERITY } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { FailurePath, Graph, GraphEdge } from "@/types";

const STATE_STROKE: Record<string, string> = {
  OK: "var(--c-success)",
  WARNING: "var(--c-warning)",
  CRITICAL: "var(--c-critical)",
  FAILED: "var(--c-critical)",
  UNKNOWN: "var(--c-unknown)",
  INFO: "var(--c-info)",
  NOTICE: "var(--c-unknown)",
  PARTIAL: "var(--c-warning)",
};

const DOMAINS = ["ALL", "kubernetes", "gitops", "pki", "network", "storage"];
const KINDS = [
  "Pod",
  "Deployment",
  "StatefulSet",
  "DaemonSet",
  "Service",
  "Secret",
  "HelmRelease",
  "Kustomization",
  "GitRepository",
];

function toFlow(
  graph: Graph,
  depth: number,
  rootId: string,
  options: { direction: "horizontal" | "vertical"; highlight: Set<string> } = {
    direction: "horizontal",
    highlight: new Set<string>(),
  },
): { nodes: Node[]; edges: Edge[] } {
  const adjacency = new Map<string, string[]>();
  for (const edge of graph.edges) {
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), edge.target]);
  }
  let allowed: Set<string>;
  if (depth <= 0 || !rootId) {
    allowed = new Set(graph.nodes.map((n) => n.id));
  } else {
    allowed = new Set([rootId]);
    let frontier = [rootId];
    for (let level = 0; level < depth; level += 1) {
      const next: string[] = [];
      for (const node of frontier) {
        for (const target of adjacency.get(node) ?? []) {
          if (!allowed.has(target)) {
            allowed.add(target);
            next.push(target);
          }
        }
      }
      frontier = next;
    }
  }

  // Deterministic layout: the same graph always renders in the same place, so
  // a refresh never shuffles the picture under the operator (spec section 42).
  const columns = new Map<number, number>();
  const nodes: Node[] = graph.nodes
    .filter((node) => allowed.has(node.id))
    .map((node, index) => {
      const column = Math.floor(index / 4);
      const row = columns.get(column) ?? 0;
      columns.set(column, row + 1);
      const position =
        options.direction === "horizontal"
          ? { x: column * 300, y: row * 90 }
          : { x: row * 260, y: column * 110 };
      return {
        id: node.id,
        position,
        data: { label: node.id, state: node.state, domain: node.domain },
        style: {
          border: `1px solid ${STATE_STROKE[node.state] ?? "var(--border)"}`,
          background: "var(--panel-2)",
          color: "var(--text)",
          borderRadius: 6,
          fontSize: 11,
          padding: 6,
          width: 220,
        },
        draggable: false,
      } satisfies Node;
    });

  const edges: Edge[] = graph.edges
    .filter((edge) => allowed.has(edge.source) && allowed.has(edge.target))
    .map((edge) => {
      const onPath = options.highlight.has(edge.id);
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        animated: onPath,
        style: {
          stroke: onPath
            ? "var(--c-critical)"
            : edge.confidence === "CONFIRMED"
              ? "var(--c-success)"
              : "var(--border-strong)",
          strokeWidth: onPath ? 2 : 1,
          strokeDasharray: edge.confidence === "CONFIRMED" || onPath ? undefined : "4 3",
        },
        labelStyle: { fill: "var(--text-muted)", fontSize: 9 },
      };
    });

  return { nodes, edges };
}

export function TopologyPage() {
  const { scope, setSelection } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const isGitOpsGraph = params.get("graph") === "gitops";

  const [kind, setKind] = useState(params.get("kind") ?? "Pod");
  const [name, setName] = useState(params.get("name") ?? "");
  const [depth, setDepth] = useState("3");
  const [domain, setDomain] = useState("ALL");
  const [hideHealthy, setHideHealthy] = useState(false);
  const [failureOnly, setFailureOnly] = useState(false);
  const [search, setSearch] = useState("");
  // Graph modes (spec sections 40, 41). "deps" is the plain dependency graph;
  // "failure" asks the engine which nodes it actually marked unhealthy;
  // "blast" follows references back to find every consumer.
  const [mode, setMode] = useState<"deps" | "failure" | "blast">("deps");
  const [direction, setDirection] = useState<"horizontal" | "vertical">("horizontal");
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // Discover selectable resources from the cluster instead of asking the
  // operator to type an identifier from memory.
  const enabled = !isGitOpsGraph;
  const podList = usePods(scope, enabled);
  const serviceList = useServices(scope, enabled);
  const workloadList = useWorkloads(scope, enabled);
  const gitopsList = useGitOps(scope, enabled);
  const certList = useCertificates(scope, enabled);

  const options = useMemo<string[]>(() => {
    switch (kind) {
      case "Pod":
        return (podList.data?.envelope.data ?? []).map((item) => item.name);
      case "Service":
        return (serviceList.data?.envelope.data ?? []).map((item) => item.name);
      case "Deployment":
      case "StatefulSet":
      case "DaemonSet":
        return (workloadList.data?.envelope.data ?? [])
          .filter((item) => item.kind === kind)
          .map((item) => item.name);
      case "GitRepository":
      case "Kustomization":
      case "HelmRelease":
        return (gitopsList.data?.envelope.data ?? [])
          .filter((item) => item.kind === kind)
          .map((item) => item.name);
      case "Secret":
        return (certList.data?.envelope.data ?? []).map((item) => item.name);
      default:
        return [];
    }
  }, [kind, podList.data, serviceList.data, workloadList.data, gitopsList.data, certList.data]);

  const loadingOptions =
    podList.isLoading || serviceList.isLoading || workloadList.isLoading || gitopsList.isLoading;

  // Auto-select the first discovered resource so the graph is never empty
  // when the cluster actually has objects of the chosen kind.
  useEffect(() => {
    if (isGitOpsGraph) return;
    if (name && options.includes(name)) return;
    if (options.length > 0) setName(options[0]);
  }, [options, name, isGitOpsGraph]);

  const dependency = useGraph(scope, kind, name, !isGitOpsGraph && Boolean(name));
  const gitops = useGitOpsGraph(scope, isGitOpsGraph);
  const failurePath = useFailurePath(
    scope,
    kind,
    name,
    !isGitOpsGraph && mode === "failure" && Boolean(name),
  );
  const consumers = useConsumers(
    scope,
    kind,
    name,
    !isGitOpsGraph && mode === "blast" && Boolean(name),
  );

  const active = isGitOpsGraph
    ? gitops
    : mode === "failure"
      ? failurePath
      : mode === "blast"
        ? consumers
        : dependency;
  const envelope = active.data?.envelope;
  const rawData = envelope?.data;

  // The three endpoints wrap the graph differently (bare Graph, FailurePath,
  // ReverseDependencies), so unwrap once here rather than at every use site.
  const graph: Graph = useMemo(() => {
    if (!rawData) return { nodes: [], edges: [] };
    const candidate = (rawData as { graph?: Graph }).graph ?? (rawData as unknown as Graph);
    if (Array.isArray(candidate?.nodes) && Array.isArray(candidate?.edges)) return candidate;
    return { nodes: [], edges: [] };
  }, [rawData]);

  const rootId = `${kind}/${name}`;

  // Edges the engine tied to an unhealthy node, and the nodes it flagged.
  const failure = rawData as FailurePath | undefined;
  const highlight = useMemo(
    () =>
      mode === "failure"
        ? new Set((failure?.pathEdges ?? []).map((edge) => edge.id))
        : new Set<string>(),
    [mode, failure],
  );
  const unhealthy = useMemo(
    () => (mode === "failure" ? new Set(failure?.unhealthy ?? []) : new Set<string>()),
    [mode, failure],
  );

  // Blast radius: follow references backwards from the selected object, so the
  // view answers "what breaks if this changes?" rather than "what does it need?".
  const blastNodes = useMemo(() => {
    if (mode !== "blast") return null;
    const reverse = new Map<string, string[]>();
    for (const edge of graph.edges) {
      reverse.set(edge.target, [...(reverse.get(edge.target) ?? []), edge.source]);
    }
    const seen = new Set<string>([rootId]);
    let frontier = [rootId];
    while (frontier.length > 0) {
      const next: string[] = [];
      for (const node of frontier) {
        for (const source of reverse.get(node) ?? []) {
          if (!seen.has(source)) {
            seen.add(source);
            next.push(source);
          }
        }
      }
      frontier = next;
    }
    return seen;
  }, [mode, graph, rootId]);

  const { nodes, edges } = useMemo(() => {
    const base = toFlow(graph, Number(depth), rootId, { direction, highlight });
    const needle = search.trim().toLowerCase();
    const visible = new Set(
      base.nodes
        .filter((node) => {
          const data = node.data as { domain?: string; state?: string };
          if (blastNodes && !blastNodes.has(node.id)) return false;
          if (domain !== "ALL" && data.domain !== domain) return false;
          if (hideHealthy && data.state === "OK") return false;
          if (failureOnly && !["FAILED", "CRITICAL", "WARNING"].includes(data.state ?? "")) {
            return false;
          }
          if (needle && !node.id.toLowerCase().includes(needle)) return false;
          return true;
        })
        .map((node) => node.id),
    );
    return {
      nodes: base.nodes.filter((node) => visible.has(node.id)),
      edges: base.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target)),
    };
  }, [graph, depth, rootId, domain, hideHealthy, failureOnly, search, direction, highlight, blastNodes]);

  return (
    <div className="space-y-3">
      <PageHeader
        title="Dependency Topology"
        subtitle="Read-only inspector — the graph cannot be edited and never mutates the cluster."
        actions={envelope ? <Freshness envelope={envelope} /> : null}
      />

      {envelope ? <PartialBanner envelope={envelope} /> : null}

      <Card>
        <CardBody className="flex flex-wrap items-center gap-2">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="w-40" aria-label="Resource kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KINDS.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isGitOpsGraph ? (
            <Badge tone="gitops">GitOps chain graph</Badge>
          ) : options.length > 0 ? (
            <Select value={name} onValueChange={setName}>
              <SelectTrigger className="w-64" aria-label="Resource name">
                <SelectValue placeholder="Select a resource" />
              </SelectTrigger>
              <SelectContent>
                {options.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={loadingOptions ? "loading resources…" : "resource name"}
              className="w-64"
              aria-label="Resource name"
            />
          )}
          <Select value={depth} onValueChange={setDepth}>
            <SelectTrigger className="w-28" aria-label="Depth">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["1", "2", "3", "0"].map((item) => (
                <SelectItem key={item} value={item}>
                  {item === "0" ? "full" : `depth ${item}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={domain} onValueChange={setDomain}>
            <SelectTrigger className="w-36" aria-label="Domain filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DOMAINS.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="search graph"
            className="w-44"
            aria-label="Search graph"
          />
          <Button
            variant={hideHealthy ? "primary" : "outline"}
            size="sm"
            onClick={() => setHideHealthy((v) => !v)}
          >
            Hide healthy
          </Button>
          {!isGitOpsGraph ? (
            <Select
              value={mode}
              onValueChange={(value) => setMode(value as "deps" | "failure" | "blast")}
            >
              <SelectTrigger className="w-40" aria-label="Graph mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="deps">Dependencies</SelectItem>
                <SelectItem value="failure">Failure path</SelectItem>
                <SelectItem value="blast">Blast radius</SelectItem>
              </SelectContent>
            </Select>
          ) : null}
          <Select
            value={direction}
            onValueChange={(value) => setDirection(value as "horizontal" | "vertical")}
          >
            <SelectTrigger className="w-32" aria-label="Layout direction">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="horizontal">Horizontal</SelectItem>
              <SelectItem value="vertical">Vertical</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant={failureOnly ? "primary" : "outline"}
            size="sm"
            onClick={() => setFailureOnly((v) => !v)}
          >
            Unhealthy only
          </Button>
          <Button
            variant={isGitOpsGraph ? "primary" : "soft"}
            size="sm"
            onClick={() => navigate(isGitOpsGraph ? "/topology" : "/topology?graph=gitops")}
          >
            <Waypoints className="h-3.5 w-3.5" />
            {isGitOpsGraph ? "Resource graph" : "GitOps chain"}
          </Button>
          {!isGitOpsGraph ? (
            <span className="text-[11px] text-text-faint">
              {loadingOptions ? "discovering resources…" : `${options.length} available`}
            </span>
          ) : null}
        </CardBody>
      </Card>

      {mode === "failure" && !isGitOpsGraph ? (
        <p className="text-[11.5px] text-text-muted">
          <strong className="font-semibold text-text">Failure path.</strong>{" "}
          {unhealthy.size > 0 ? (
            <>
              {unhealthy.size} node{unhealthy.size === 1 ? "" : "s"} named by the engine&apos;s
              findings; the highlighted edges are the ones attached to them.{" "}
            </>
          ) : (
            <>
              No node in this graph was named by the engine&apos;s findings, so nothing is
              highlighted.{" "}
            </>
          )}
          {failure?.healthSource ? (
            <>
              Health is read from <span className="mono">{failure.healthSource}</span> — the
              dependency report describes structure, not state.{" "}
            </>
          ) : null}
          {failure?.note ?? ""}
        </p>
      ) : null}
      {mode === "blast" && !isGitOpsGraph ? (
        <p className="text-[11.5px] text-text-muted">
          <strong className="font-semibold text-text">Blast radius.</strong> Following references
          backwards from <span className="mono">{rootId}</span> found{" "}
          {Math.max((blastNodes?.size ?? 1) - 1, 0)} consumer
          {Math.max((blastNodes?.size ?? 1) - 1, 0) === 1 ? "" : "s"}. Relationships are the
          engine&apos;s own edges, so they carry an explicit confidence rather than a claim of
          causality.
        </p>
      ) : null}

      <Card>
        <CardBody className="p-0">
          {active.isLoading ? <LoadingRows rows={8} /> : null}
          {envelope?.errors.length ? (
            <div className="p-3">
              <ErrorState envelope={envelope} onRetry={() => void active.refetch()} />
            </div>
          ) : null}
          {!active.isLoading && !envelope?.errors.length && nodes.length === 0 ? (
            <EmptyState
              kind={name || isGitOpsGraph ? "EMPTY" : "UNAVAILABLE"}
              title={name || isGitOpsGraph ? "No dependency rows found" : "Select a resource"}
              detail={
                name || isGitOpsGraph
                  ? "The engine reported no dependency edges for this selection."
                  : "Enter a resource name to trace its dependency graph, or open the GitOps graph from the GitOps page."
              }
            />
          ) : null}
          {nodes.length > 0 ? (
            <div style={{ height: 560 }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                fitView
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
                proOptions={{ hideAttribution: true }}
                onNodeClick={(_, node) => {
                  const [nodeKind, ...rest] = node.id.split("/");
                  if (nodeKind && rest.length) setSelection({ kind: nodeKind, name: rest.join("/") });
                }}
                onEdgeClick={(_, edge) => {
                  setSelectedEdge(graph.edges.find((item) => item.id === edge.id) ?? null);
                }}
              >
                <Background color="var(--border)" gap={20} />
                <Controls showInteractive={false} />
                <MiniMap
                  pannable
                  zoomable
                  nodeColor={(node) =>
                    STATE_STROKE[(node.data as { state?: string }).state ?? "UNKNOWN"] ??
                    "var(--c-unknown)"
                  }
                />
              </ReactFlow>
            </div>
          ) : null}

          {/* Edge evidence (spec sections 37, 347): every relationship can say
              why it exists, and never claims more than the engine reported. */}
          {selectedEdge ? (
            <div className="border-t border-border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-[12px] font-semibold uppercase tracking-wide text-text-muted">
                    Relationship
                  </h3>
                  <div className="mono mt-0.5 break-all text-[12.5px] text-text">
                    {selectedEdge.source} → {selectedEdge.target}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setSelectedEdge(null)}>
                  Close
                </Button>
              </div>
              <dl className="mt-1 max-w-3xl">
                <Field label="Kind">
                  <span className="mono">{selectedEdge.label}</span>
                </Field>
                <Field label="Confidence">
                  <ConfidenceTag confidence={selectedEdge.confidence} />
                </Field>
                <Field label="Evidence" mono>
                  <span title={selectedEdge.evidence}>
                    {selectedEdge.evidence || "the engine reported this edge without a source line"}
                  </span>
                </Field>
                <Field label="Source">
                  <span className="mono">{envelope?.source ?? "UNAVAILABLE"}</span>
                </Field>
              </dl>
              <p className="mt-1 text-[11px] text-text-faint">
                Evidence is the engine&apos;s own report line. DevOpsSentinel does not infer a
                relationship the engine did not state.
              </p>
            </div>
          ) : null}
        </CardBody>
      </Card>

      <div className="flex flex-wrap gap-3 text-[11px] text-text-muted">
        {(["OK", "WARNING", "CRITICAL", "UNKNOWN"] as const).map((key) => (
          <span key={key} className={`inline-flex items-center gap-1 ${SEVERITY[key].className}`}>
            <span aria-hidden="true">{SEVERITY[key].glyph}</span> {SEVERITY[key].label}
          </span>
        ))}
        <span className="text-text-faint">
          Solid edge = CONFIRMED · dashed edge = inferred (see confidence label)
        </span>
      </div>
    </div>
  );
}

