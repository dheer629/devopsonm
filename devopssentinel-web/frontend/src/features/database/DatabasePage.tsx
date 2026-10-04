import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import {
  useDatabase,
  useDatabaseServices,
  usePods,
  useSqlConsole,
  useStorage,
  useSystem,
} from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  EmptyState,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  RawView,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { reportText } from "@/lib/format";
import { useApp } from "@/state/AppContext";
import type { DbServiceResource } from "@/types";

import { SqlConsole } from "./SqlConsole";

/** Read-only PostgreSQL / generic DB discovery.
 *
 *  Three views, all backed by the engine: the parsed **Services** table, the
 *  **Data** view (which pods and PVCs actually back each discovered database)
 *  and the raw **Report**. Row-level SQL stays in the engine's interactive
 *  console: credentials must never traverse the browser.
 */
export function DatabasePage() {
  const { scope, setSelection } = useApp();
  const services = useDatabaseServices(scope);
  const report = useDatabase(scope);
  const pods = usePods(scope);
  const storage = useStorage(scope);
  const system = useSystem();

  const rows = services.data?.envelope.data ?? [];
  const podRows = pods.data?.envelope.data ?? [];
  const pvcRows = storage.data?.envelope.data ?? [];

  const ready = rows.filter((row) => row.status === "OK").length;
  const psql = Boolean(system.data?.data.capabilities.psql);
  const consoleStatus = useSqlConsole();
  const consoleEnabled = Boolean(
    consoleStatus.data?.data.enabled && consoleStatus.data?.data.driverAvailable,
  );

  const lines = useMemo(
    () =>
      reportText(report.data?.envelope.data)
        .split("\n")
        .filter((line) => line.trim() !== ""),
    [report.data],
  );

  // A discovered database is only real if a pod answers on the reported
  // endpoint IP. Join the engine's discovery table with the pod inventory.
  const backing = useMemo(() => {
    const byIp = new Map(podRows.map((pod) => [pod.ip, pod]));
    return rows.map((row) => {
      const pod = byIp.get(row.ready_endpoint);
      const volumes = pod ? pvcRows.filter((pvc) => pvc.consumers.includes(pod.name)) : [];
      return { row, pod, volumes };
    });
  }, [rows, podRows, pvcRows]);

  const columns = useMemo<ColumnDef<DbServiceResource, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Service",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "type", header: "Type" },
      {
        accessorKey: "port",
        header: "Port",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "cluster_ip",
        header: "Cluster IP",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "ready_endpoint",
        header: "Ready endpoint",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "database",
        header: "Database",
        cell: (info) => <span className="text-text-muted">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "username",
        header: "Username",
        cell: (info) => <span className="text-text-muted">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
      },
    ],
    [],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="Database"
        subtitle={
          <>
            {rows.length} discovered database {rows.length === 1 ? "service" : "services"} · {ready}{" "}
            with a ready endpoint · metadata only, credentials are never read
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="warning">read-only queries only</Badge>
            {services.data ? <Freshness envelope={services.data.envelope} /> : null}
          </div>
        }
      />

      {services.data ? <PartialBanner envelope={services.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Data access</CardTitle>
          <Badge tone={psql ? "info" : "unknown"}>
            {psql ? "psql present" : "psql not installed"}
          </Badge>
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Discovered services" value={String(rows.length)} />
          <Metric label="Ready endpoints" value={`${ready} / ${rows.length}`} />
          <Metric label="psql client" value={psql ? "AVAILABLE" : "NOT INSTALLED"} />
          <Metric label="SQL console" value={consoleEnabled ? "ENABLED" : "DISABLED"} />
          <Metric label="Row-level data" value={consoleEnabled ? "SQL TAB" : "CLI ONLY"} />
          <p className="text-[11.5px] text-text-muted sm:col-span-2 lg:col-span-5">
            Use the <span className="mono">SQL</span> tab for a read-only session (opt-in with{" "}
            <span className="mono">DSWEB_ENABLE_SQL_CONSOLE=1</span>; credentials are used for one
            request and never stored). Otherwise run{" "}
            <span className="mono">
              bash DevOps_K8s_Sentinel_FINAL_GP.sh --context {scope.context || "&lt;ctx&gt;"}{" "}
              --namespace {scope.namespace || "&lt;ns&gt;"}
            </span>{" "}
            and choose <span className="mono">PostgreSQL / generic DB → read-only checks</span>.
          </p>
        </CardBody>
      </Card>

      <Tabs defaultValue="services">
        <TabsList>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="data">Data</TabsTrigger>
          <TabsTrigger value="sql">SQL</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>

        <TabsContent value="services">
          <Card>
            <CardBody className="p-0">
              {services.isLoading ? <LoadingRows /> : null}
              {services.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState
                    envelope={services.data.envelope}
                    onRetry={() => void services.refetch()}
                  />
                </div>
              ) : null}
              {services.data && !services.data.envelope.errors.length ? (
                <DataTable
                  data={rows}
                  columns={columns}
                  exportName="devopssentinel-database-services"
                  emptyMessage={`No database service matched in ${scope.namespace || "this namespace"}. Names containing postgres, pgsql, database or genericdb are reported.`}
                  onRowClick={(row) => setSelection({ kind: "Service", name: row.name })}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="data">
          <div className="space-y-3">
            {backing.length === 0 ? (
              <Card>
                <CardBody>
                  <EmptyState
                    title="No database to describe"
                    detail="Deploy a Service whose name contains postgres, pgsql, database or genericdb and it will appear here with its backing pods and volumes."
                  />
                </CardBody>
              </Card>
            ) : null}
            {backing.map(({ row, pod, volumes }) => (
              <Card key={row.name}>
                <CardHeader>
                  <CardTitle>
                    <span className="mono">{row.name}</span>
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{row.type}</Badge>
                    <StatusPill status={row.status} />
                  </div>
                </CardHeader>
                <CardBody className="space-y-2 text-[12px]">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Metric label="Port" value={row.port || "—"} />
                    <Metric label="Cluster IP" value={row.cluster_ip || "—"} />
                    <Metric label="Endpoint" value={row.ready_endpoint || "—"} />
                    <Metric label="Namespace" value={row.namespace || scope.namespace || "—"} />
                  </div>
                  {pod ? (
                    <div className="rounded-md border border-border p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] uppercase tracking-wide text-text-faint">
                          Backing pod
                        </span>
                        <span className="mono text-[12px]">{pod.name}</span>
                        <StatusPill status={pod.status} />
                        <span className="text-[11.5px] text-text-muted">
                          ready {pod.ready || "—"} · restarts {pod.restarts} · node {pod.node || "—"}
                        </span>
                      </div>
                      <div className="mt-1 text-[11.5px] text-text-muted">
                        {volumes.length === 0
                          ? "No PersistentVolumeClaim reported for this pod (ephemeral storage)."
                          : `Storage: ${volumes
                              .map((pvc) => `${pvc.name} (${pvc.capacity || "?"}, ${pvc.status})`)
                              .join(", ")}`}
                      </div>
                    </div>
                  ) : (
                    <p className="text-[11.5px] text-warning">
                      No running pod answers on {row.ready_endpoint || "the reported endpoint"} — the
                      Service has no live backend in this namespace.
                    </p>
                  )}
                  <p className="text-[11px] text-text-faint">
                    Database name, schema and rows are not extracted from Secret payloads. Values
                    shown as UNKNOWN are intentionally not read.
                  </p>
                </CardBody>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="sql">
          <SqlConsole />
        </TabsContent>

        <TabsContent value="report">
          <Card>
            <CardHeader>
              <CardTitle>Engine report</CardTitle>
              <Badge tone="neutral">{lines.length} lines</Badge>
            </CardHeader>
            <CardBody className="p-0">
              {report.isLoading ? <LoadingRows /> : null}
              {report.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState
                    envelope={report.data.envelope}
                    onRetry={() => void report.refetch()}
                  />
                </div>
              ) : null}
              {lines.length > 0 ? (
                <pre className="mono max-h-[520px] overflow-auto whitespace-pre-wrap bg-bg-elevated p-3 text-[11.5px] text-text">
                  {lines.join("\n")}
                </pre>
              ) : null}
              {!report.isLoading && lines.length === 0 && !report.data?.envelope.errors.length ? (
                <p className="p-3 text-[12.5px] text-text-muted">
                  No data was reported for this scope. Select a namespace that contains a database
                  Service.
                </p>
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="raw">
          <RawView raw={report.data?.raw ?? services.data?.raw} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border px-2 py-1">
      <div className="text-[10.5px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mono truncate text-[12.5px] text-text" title={value}>
        {value}
      </div>
    </div>
  );
}

