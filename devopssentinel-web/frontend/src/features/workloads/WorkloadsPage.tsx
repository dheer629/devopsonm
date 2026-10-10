import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { usePods, useNodeMetrics, usePodMetrics, useWorkloads } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import { ErrorState, Freshness, LoadingRows, PageHeader, PartialBanner, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DEFAULT_USAGE_RANGE,
  ObservationControl,
  RangeSelect,
  rangeSummary,
  UsageBar,
  UsageChart,
  usageRangeMs,
  useUsageHistory,
  windowedSeries,
  type UsageRangeId,
} from "@/components/Usage";
import { formatBytes, formatCores } from "@/lib/format";
import { OBSERVE_INTERVAL_MS } from "@/lib/observation";
import { severityRank } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { Pod, PodUsage, Workload } from "@/types";

export function WorkloadsPage() {
  const { scope, setSelection, observe, setObserve } = useApp();
  const navigate = useNavigate();
  const workloads = useWorkloads(scope);
  const pods = usePods(scope);
  // The charts observe the cluster themselves: the Metrics API is instantaneous,
  // so a trend only exists if this page keeps sampling. Pausing it stops both
  // metrics reads and leaves the collected history in place. (If the LIVE switch
  // is also on it re-reads the same two queries; each read is just another
  // sample, so the two controls never disagree about what was measured.)
  const observeMs = observe ? OBSERVE_INTERVAL_MS : undefined;
  const nodeMetrics = useNodeMetrics(scope.context ?? "", Boolean(scope.context), observeMs);
  const podMetrics = usePodMetrics(scope, Boolean(scope.namespace), observeMs);

  const usageByName = useMemo(() => {
    const map = new Map<string, PodUsage>();
    for (const row of podMetrics.data?.data?.pods ?? []) map.set(row.name, row);
    return map;
  }, [podMetrics.data]);

  const podCpuMax = useMemo(
    () => Math.max(1, ...Array.from(usageByName.values(), (row) => row.cpuMillicores)),
    [usageByName],
  );
  const podMemoryMax = useMemo(
    () => Math.max(1, ...Array.from(usageByName.values(), (row) => row.memoryBytes)),
    [usageByName],
  );

  const nodes = nodeMetrics.data?.data?.nodes ?? [];
  const nodeStamp = nodeMetrics.data?.timestamp;
  const nodeCores = useMemo(
    () => nodes.reduce((total, node) => total + node.cpuMillicores, 0),
    [nodes],
  );
  const nodeMemory = useMemo(
    () => nodes.reduce((total, node) => total + node.memoryBytes, 0),
    [nodes],
  );
  // Chart only what was actually measured. An UNAVAILABLE envelope still carries
  // a fresh timestamp, so passing a value unconditionally appends a zero that no
  // `kubectl top` ever reported -- and the chart then draws an axis for it while
  // the honest "unavailable" message stays unreachable.
  const nodeUsageMeasured = nodeMetrics.data?.source === "LIVE" && nodes.length > 0;
  const cpuHistory = useUsageHistory(nodeStamp, nodeUsageMeasured ? nodeCores : undefined);
  const memoryHistory = useUsageHistory(nodeStamp, nodeUsageMeasured ? nodeMemory : undefined);
  const [range, setRange] = useState<UsageRangeId>(DEFAULT_USAGE_RANGE);
  const rangeMs = usageRangeMs(range);
  const cpuWindow = useMemo(() => windowedSeries(cpuHistory, rangeMs), [cpuHistory, rangeMs]);
  const memoryWindow = useMemo(
    () => windowedSeries(memoryHistory, rangeMs),
    [memoryHistory, rangeMs],
  );
  const cpuNote = rangeSummary(cpuWindow, range);
  const memoryNote = rangeSummary(memoryWindow, range);
  const metricsUnavailable = (nodeMetrics.data?.errors.length ?? 0) > 0;

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
      {
        id: "cpu",
        header: "CPU (cores)",
        accessorFn: (row) => usageByName.get(row.name)?.cpuMillicores ?? 0,
        cell: (info) => {
          const usage = usageByName.get((info.row.original as Pod).name);
          if (!usage) return <span className="text-text-faint">—</span>;
          return (
            <UsageBar
              value={usage.cpuMillicores}
              max={podCpuMax}
              label={formatCores(usage.cpuMillicores)}
              color="var(--c-success)"
            />
          );
        },
      },
      {
        id: "memory",
        header: "Memory (bytes)",
        accessorFn: (row) => usageByName.get(row.name)?.memoryBytes ?? 0,
        cell: (info) => {
          const usage = usageByName.get((info.row.original as Pod).name);
          if (!usage) return <span className="text-text-faint">—</span>;
          return (
            <UsageBar
              value={usage.memoryBytes}
              max={podMemoryMax}
              label={formatBytes(usage.memoryBytes)}
              color="var(--c-kubernetes)"
            />
          );
        },
      },
    ],
    [usageByName, podCpuMax, podMemoryMax],
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
            <RangeSelect value={range} onChange={setRange} />
            <Badge tone="neutral">namespace {scope.namespace || "—"}</Badge>
            {workloads.data ? <Freshness envelope={workloads.data.envelope} /> : null}
          </div>
        }
      />

      {workloads.data ? <PartialBanner envelope={workloads.data.envelope} /> : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>CPU usage</CardTitle>
            <span className="flex items-center gap-2">
              <span className="mono text-[11px] text-text-muted">
                {metricsUnavailable ? "metrics unavailable" : `${nodes.length} nodes`}
              </span>
              <ObservationControl observing={observe} onToggle={() => setObserve(!observe)} />
            </span>
          </CardHeader>
          <CardBody className="pt-1">
            <UsageChart
              points={cpuWindow}
              kind="cpu"
              color="var(--c-success)"
              note={cpuNote}
              emptyMessage={
                metricsUnavailable
                  ? "Metrics API unavailable — install metrics-server to chart live usage."
                  : undefined
              }
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Memory usage</CardTitle>
            <span className="flex items-center gap-2">
              <span className="mono text-[11px] text-text-muted">
                {metricsUnavailable ? "metrics unavailable" : `${nodes.length} nodes`}
              </span>
              <ObservationControl observing={observe} onToggle={() => setObserve(!observe)} />
            </span>
          </CardHeader>
          <CardBody className="pt-1">
            <UsageChart
              points={memoryWindow}
              kind="memory"
              color="var(--c-kubernetes)"
              note={memoryNote}
              emptyMessage={
                metricsUnavailable
                  ? "Metrics API unavailable — install metrics-server to chart live usage."
                  : undefined
              }
            />
          </CardBody>
        </Card>
      </div>

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
