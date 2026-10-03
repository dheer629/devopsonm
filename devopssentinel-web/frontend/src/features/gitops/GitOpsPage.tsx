import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useGitOps, useGitOpsGraph } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  ConfidenceTag,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { severityRank } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { GitOpsObject } from "@/types";

const KINDS = [
  "ALL",
  "GitRepository",
  "OCIRepository",
  "HelmRepository",
  "Kustomization",
  "HelmRelease",
];

export function GitOpsPage() {
  const { scope, setSelection } = useApp();
  const gitops = useGitOps(scope);
  const graph = useGitOpsGraph(scope);
  const [kind, setKind] = useState("ALL");

  const rows = useMemo(() => {
    const all = [...(gitops.data?.envelope.data ?? [])].sort(
      (a, b) => severityRank(a.status) - severityRank(b.status),
    );
    return kind === "ALL" ? all : all.filter((row) => row.kind === kind);
  }, [gitops.data, kind]);

  const summary = useMemo(() => {
    const all = gitops.data?.envelope.data ?? [];
    return {
      total: all.length,
      ready: all.filter((o) => o.ready === true).length,
      failed: all.filter((o) => o.ready === false).length,
      suspended: all.filter((o) => o.suspended).length,
    };
  }, [gitops.data]);

  const columns = useMemo<ColumnDef<GitOpsObject, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "kind", header: "Kind" },
      {
        accessorKey: "ready",
        header: "Ready",
        cell: (info) => {
          const value = info.getValue() as boolean | null;
          if (value === null) return <StatusPill status="UNKNOWN" />;
          return <StatusPill status={value ? "OK" : "FAILED"} label={value ? "Ready" : "Failed"} />;
        },
      },
      {
        accessorKey: "suspended",
        header: "Suspended",
        cell: (info) => (info.getValue() ? "yes" : "no"),
      },
      {
        accessorKey: "revision",
        header: "Revision",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "applied_revision",
        header: "Applied",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      { accessorKey: "message", header: "Message" },
    ],
    [],
  );

  const rawChain = graph.data?.envelope.data;
  const chain =
    rawChain && Array.isArray(rawChain.nodes) && Array.isArray(rawChain.edges)
      ? rawChain
      : { nodes: [], edges: [] };

  return (
    <div className="space-y-3">
      <PageHeader
        title="GitOps Command Center"
        subtitle={
          <>
            {summary.ready} / {summary.total} ready · {summary.failed} failed · {summary.suspended}{" "}
            suspended
          </>
        }
        actions={gitops.data ? <Freshness envelope={gitops.data.envelope} /> : null}
      />

      {gitops.data ? <PartialBanner envelope={gitops.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Flux chain</CardTitle>
          <Badge tone="gitops">source → kustomization → helmrelease → workload</Badge>
        </CardHeader>
        <CardBody className="space-y-2">
          {chain.nodes.length === 0 ? (
            <p className="text-[12px] text-text-muted">
              No Flux chain was reported for this scope. GitOps is an enhancement — the rest of the
              console continues to work.
            </p>
          ) : (
            <ul className="space-y-1">
              {chain.edges.map((edge) => (
                <li key={edge.id} className="flex flex-wrap items-center gap-2">
                  <span className="mono text-[11.5px] text-text">{edge.source}</span>
                  <span className="text-[11px] text-text-muted">—{edge.label}→</span>
                  <span className="mono text-[11.5px] text-text">{edge.target}</span>
                  <ConfidenceTag confidence={edge.confidence} />
                </li>
              ))}
            </ul>
          )}
          <Link to="/topology?graph=gitops" className="text-[11.5px] text-accent">
            Open interactive topology →
          </Link>
        </CardBody>
      </Card>

      <Tabs value={kind} onValueChange={setKind}>
        <TabsList>
          {KINDS.map((item) => (
            <TabsTrigger key={item} value={item}>
              {item === "ALL" ? "All kinds" : item}
            </TabsTrigger>
          ))}
        </TabsList>
        {KINDS.map((item) => (
          <TabsContent key={item} value={item}>
            <Card>
              <CardBody className="p-0">
                {gitops.isLoading ? <LoadingRows /> : null}
                {gitops.data?.envelope.errors.length ? (
                  <div className="p-3">
                    <ErrorState
                      envelope={gitops.data.envelope}
                      onRetry={() => void gitops.refetch()}
                    />
                  </div>
                ) : null}
                {gitops.data && !gitops.data.envelope.errors.length ? (
                  <DataTable
                    data={rows}
                    columns={columns}
                    exportName="devopssentinel-gitops"
                    emptyMessage="No GitOps objects of this kind were reported."
                    onRowClick={(obj) => setSelection({ kind: obj.kind, name: obj.name })}
                  />
                ) : null}
              </CardBody>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <p className="text-[11px] text-text-muted">
        Supervision mode never offers Reconcile, Suspend, Resume, Upgrade or Rollback. Generation and
        revision differences may be reconciliation lag, not manifest drift.
      </p>
    </div>
  );
}
