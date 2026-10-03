import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";

import { usePods, useWorkloads } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import { ErrorState, Freshness, LoadingRows, PageHeader, PartialBanner, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { severityRank } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { Pod, Workload } from "@/types";

export function WorkloadsPage() {
  const { scope, setSelection } = useApp();
  const navigate = useNavigate();
  const workloads = useWorkloads(scope);
  const pods = usePods(scope);

  const workloadRows = useMemo(
    () =>
      [...(workloads.data?.envelope.data ?? [])].sort(
        (a, b) => severityRank(a.status) - severityRank(b.status),
      ),
    [workloads.data],
  );
  const podRows = useMemo(
    () =>
      [...(pods.data?.envelope.data ?? [])].sort(
        (a, b) => severityRank(a.status) - severityRank(b.status),
      ),
    [pods.data],
  );

  const podColumns = useMemo<ColumnDef<Pod, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "phase", header: "Phase" },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
        sortingFn: (a, b) => severityRank(a.original.status) - severityRank(b.original.status),
      },
      { accessorKey: "ready", header: "Ready" },
      {
        accessorKey: "restarts",
        header: "Restarts",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "node", header: "Node" },
      { accessorKey: "age", header: "Age" },
    ],
    [],
  );

  const workloadColumns = useMemo<ColumnDef<Workload, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "kind", header: "Kind" },
      { accessorKey: "ready", header: "Ready" },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
        sortingFn: (a, b) => severityRank(a.original.status) - severityRank(b.original.status),
      },
      { accessorKey: "restarts", header: "Restarts" },
      { accessorKey: "node", header: "Node" },
      { accessorKey: "age", header: "Age" },
      { accessorKey: "cpu", header: "CPU" },
      { accessorKey: "memory", header: "Memory" },
      { accessorKey: "gitops", header: "GitOps" },
    ],
    [],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="Workloads"
        subtitle={
          <>
            {podRows.length} pods · {workloadRows.length} workloads · ordered critical → healthy
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="neutral">namespace {scope.namespace || "—"}</Badge>
            {workloads.data ? <Freshness envelope={workloads.data.envelope} /> : null}
          </div>
        }
      />

      {workloads.data ? <PartialBanner envelope={workloads.data.envelope} /> : null}

      <Tabs defaultValue="pods">
        <TabsList>
          <TabsTrigger value="pods">Pods</TabsTrigger>
          <TabsTrigger value="workloads">Workloads</TabsTrigger>
        </TabsList>

        <TabsContent value="pods">
          <Card>
            <CardBody className="p-0">
              {pods.isLoading ? <LoadingRows /> : null}
              {pods.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState envelope={pods.data.envelope} onRetry={() => void pods.refetch()} />
                </div>
              ) : null}
              {pods.data && !pods.data.envelope.errors.length ? (
                <DataTable
                  data={podRows}
                  columns={podColumns}
                  exportName="devopssentinel-pods"
                  emptyMessage={`No pods found in ${scope.namespace || "the selected namespace"}.`}
                  onRowClick={(pod) => {
                    setSelection({ kind: "Pod", name: pod.name });
                    navigate(`/workloads/pods/${pod.name}`);
                  }}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="workloads">
          <Card>
            <CardBody className="p-0">
              {workloads.isLoading ? <LoadingRows /> : null}
              {workloads.data && !workloads.data.envelope.errors.length ? (
                <DataTable
                  data={workloadRows}
                  columns={workloadColumns}
                  exportName="devopssentinel-workloads"
                  emptyMessage="No workloads reported."
                  onRowClick={(workload) => setSelection({ kind: workload.kind, name: workload.name })}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>
      </Tabs>

      <p className="text-[11px] text-text-muted">
        Identifiers are never silently truncated; hover a cell or open the inspector for full values.{" "}
        <Link to="/topology" className="text-accent">
          Open dependency topology →
        </Link>
      </p>
    </div>
  );
}
