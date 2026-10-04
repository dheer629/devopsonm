import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { useKafka, useKafkaServices, usePods, useSystem } from "@/api/queries";
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
import type { KafkaServiceResource } from "@/types";

/** Read-only Kafka discovery.
 *
 *  **Brokers** shows the parsed discovery table, **Topics** shows whether topic
 *  data can actually be read (broker + `kafka-topics` availability, bootstrap
 *  candidates and the exact engine command) and **Data** joins each broker to
 *  its backing pod. Topic listing itself stays in the engine console.
 */
export function KafkaPage() {
  const { scope, setSelection } = useApp();
  const services = useKafkaServices(scope);
  const report = useKafka(scope);
  const pods = usePods(scope);
  const system = useSystem();

  const rows = services.data?.envelope.data ?? [];
  const podRows = pods.data?.envelope.data ?? [];
  const cli = Boolean(system.data?.data.capabilities.kafka);

  const lines = useMemo(
    () =>
      reportText(report.data?.envelope.data)
        .split("\n")
        .filter((line) => line.trim() !== ""),
    [report.data],
  );

  const backing = useMemo(() => {
    // A broker Service is backed by the pods that answer on its endpoints.
    const byName = new Map<string, string[]>();
    for (const row of rows) {
      byName.set(
        row.name,
        podRows.filter((pod) => pod.name.startsWith(row.name)).map((pod) => pod.name),
      );
    }
    return byName;
  }, [rows, podRows]);

  const columns = useMemo<ColumnDef<KafkaServiceResource, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Service",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "type", header: "Type" },
      {
        accessorKey: "cluster_ip",
        header: "Cluster IP",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "ports",
        header: "Ports",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "bootstrap",
        header: "Bootstrap candidate",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
      },
    ],
    [],
  );

  const engineCmd = `bash DevOps_K8s_Sentinel_FINAL_GP.sh --context ${
    scope.context || "<ctx>"
  } --namespace ${scope.namespace || "<ns>"}`;

  return (
    <div className="space-y-3">
      <PageHeader
        title="Kafka"
        subtitle={
          <>
            {rows.length} discovered broker {rows.length === 1 ? "service" : "services"} · bootstrap
            endpoints and topic availability · no credentials exposed
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="warning">no credentials exposed</Badge>
            {services.data ? <Freshness envelope={services.data.envelope} /> : null}
          </div>
        }
      />

      {services.data ? <PartialBanner envelope={services.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Topic data availability</CardTitle>
          <Badge tone={cli && rows.length > 0 ? "info" : "unknown"}>
            {cli && rows.length > 0 ? "broker + CLI detected" : "not readable here"}
          </Badge>
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Brokers discovered" value={String(rows.length)} />
          <Metric label="kafka-topics CLI" value={cli ? "AVAILABLE" : "NOT INSTALLED"} />
          <Metric
            label="Bootstrap candidates"
            value={String(rows.filter((row) => row.bootstrap).length)}
          />
          <Metric label="Topic listing" value="CLI ONLY" />
          <div className="space-y-1 sm:col-span-2 lg:col-span-4">
            {rows.length === 0 ? (
              <p className="text-[11.5px] text-warning">
                No Kafka broker Service was reported in{" "}
                <span className="mono">{scope.namespace || "this namespace"}</span>, so there are no
                topics to list. Services whose name or labels contain <span className="mono">kafka</span>{" "}
                are reported.
              </p>
            ) : null}
            <p className="text-[11.5px] text-text-muted">
              Topic, partition and consumer-group data requires an authenticated broker session. The
              engine performs that in its interactive console, so credentials never traverse the
              browser. Run <span className="mono">{engineCmd}</span> and choose{" "}
              <span className="mono">Kafka → List topics</span>.
            </p>
          </div>
        </CardBody>
      </Card>

      <Tabs defaultValue="brokers">
        <TabsList>
          <TabsTrigger value="brokers">Brokers</TabsTrigger>
          <TabsTrigger value="topics">Topics</TabsTrigger>
          <TabsTrigger value="data">Data</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>

        <TabsContent value="brokers">
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
                  exportName="devopssentinel-kafka-brokers"
                  emptyMessage={`No Kafka Service matched in ${scope.namespace || "this namespace"}.`}
                  onRowClick={(row) => setSelection({ kind: "Service", name: row.name })}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="topics">
          <Card>
            <CardHeader>
              <CardTitle>Topics</CardTitle>
              <Badge tone="unknown">UNAVAILABLE</Badge>
            </CardHeader>
            <CardBody className="space-y-2">
              {rows.length === 0 ? (
                <EmptyState
                  title="No broker to query"
                  detail="Deploy a Service named kafka (or labelled kafka) and it will be reported here with a bootstrap candidate."
                />
              ) : (
                <ul className="space-y-1">
                  {rows.map((row) => (
                    <li
                      key={row.name}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-2 py-1"
                    >
                      <span className="mono text-[11.5px]">{row.bootstrap || row.name}</span>
                      <span className="text-[11px] text-text-muted">
                        {row.bootstrap
                          ? "run: kafka-topics.sh --bootstrap-server " + row.bootstrap + " --list"
                          : "no usable port reported"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11.5px] text-text-muted">
                Topic data is not read by the browser adapter. This page proves the broker exists and
                gives you the exact bootstrap address; the engine console lists the topics.
              </p>
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="data">
          <div className="space-y-3">
            {rows.length === 0 ? (
              <Card>
                <CardBody>
                  <EmptyState
                    title="No broker to describe"
                    detail="Deploy a Service named kafka and it will appear here with its backing pods."
                  />
                </CardBody>
              </Card>
            ) : null}
            {rows.map((row) => {
              const consumers = backing.get(row.name) ?? [];
              return (
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
                      <Metric label="Cluster IP" value={row.cluster_ip || "—"} />
                      <Metric label="Ports" value={row.ports || "—"} />
                      <Metric label="Bootstrap" value={row.bootstrap || "—"} />
                      <Metric label="Namespace" value={row.namespace || scope.namespace || "—"} />
                    </div>
                    <div className="text-[11.5px] text-text-muted">
                      {consumers.length === 0
                        ? "No pod with a matching name prefix was reported — the Service may have no live backend."
                        : `Backing pods: ${consumers.join(", ")}`}
                    </div>
                  </CardBody>
                </Card>
              );
            })}
          </div>
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
                  No data was reported for this scope. Select a namespace that contains a Kafka
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

