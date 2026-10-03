import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useGitOpsGraph, useGraph } from "@/api/queries";
import {
  EmptyState,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
} from "@/components/common";
import { Button } from "@/components/ui/button";
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
import type { Graph } from "@/types";

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

function toFlow(graph: Graph, depth: number, rootId: string): { nodes: Node[]; edges: Edge[] } {
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

  const columns = new Map<number, number>();
  const nodes: Node[] = graph.nodes
    .filter((node) => allowed.has(node.id))
    .map((node, index) => {
      const column = Math.floor(index / 4);
      const row = columns.get(column) ?? 0;
      columns.set(column, row + 1);
      return {
        id: node.id,
        position: { x: column * 300, y: row * 90 },
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
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      style: {
        stroke: edge.confidence === "CONFIRMED" ? "var(--c-success)" : "var(--border-strong)",
        strokeDasharray: edge.confidence === "CONFIRMED" ? undefined : "4 3",
      },
      labelStyle: { fill: "var(--text-muted)", fontSize: 9 },
    }));

  return { nodes, edges };
}

export function TopologyPage() {
  const { scope, setSelection } = useApp();
  const [params] = useSearchParams();
  const isGitOpsGraph = params.get("graph") === "gitops";

  const [kind, setKind] = useState(params.get("kind") ?? "Pod");
  const [name, setName] = useState(params.get("name") ?? "");
  const [depth, setDepth] = useState("3");
  const [domain, setDomain] = useState("ALL");
  const [hideHealthy, setHideHealthy] = useState(false);
  const [failureOnly, setFailureOnly] = useState(false);
  const [search, setSearch] = useState("");

  const dependency = useGraph(scope, kind, name, !isGitOpsGraph && Boolean(name));
  const gitops = useGitOpsGraph(scope, isGitOpsGraph);

  const active = isGitOpsGraph ? gitops : dependency;
  const envelope = active.data?.envelope;
  const rawGraph = envelope?.data;
  const graph: Graph =
    rawGraph && Array.isArray(rawGraph.nodes) && Array.isArray(rawGraph.edges)
      ? rawGraph
      : { nodes: [], edges: [] };
  const rootId = `${kind}/${name}`;

  const { nodes, edges } = useMemo(() => {
    const base = toFlow(graph, Number(depth), rootId);
    const needle = search.trim().toLowerCase();
    const visible = new Set(
      base.nodes
        .filter((node) => {
          const data = node.data as { domain?: string; state?: string };
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
  }, [graph, depth, rootId, domain, hideHealthy, failureOnly, search]);

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
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="resource name"
            className="w-56"
            aria-label="Resource name"
          />
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
          <Button
            variant={failureOnly ? "primary" : "outline"}
            size="sm"
            onClick={() => setFailureOnly((v) => !v)}
          >
            Failure path
          </Button>
        </CardBody>
      </Card>

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

