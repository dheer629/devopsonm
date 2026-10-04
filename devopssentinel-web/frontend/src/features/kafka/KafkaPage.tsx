import type { ColumnDef } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";

import {
  useKafka,
  useKafkaConsole,
  useKafkaServices,
  useListTopics,
  usePods,
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
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { reportText } from "@/lib/format";
import { DEMO_KAFKA_PORT, resolveLiveHost } from "@/lib/live";
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

  const consoleStatus = useKafkaConsole();
  const listTopics = useListTopics();
  const suggestedHost = resolveLiveHost(
    consoleStatus.data?.data.defaultHost,
    window.location.hostname,
  );
  const [brokerHost, setBrokerHost] = useState(suggestedHost);
  const [hostTouched, setHostTouched] = useState(false);
  const [brokerPort, setBrokerPort] = useState(DEMO_KAFKA_PORT);
  const topicsEnabled = Boolean(consoleStatus.data?.data.enabled);
  const listing = listTopics.data?.data;

  // The node address arrives with the console status; adopt it until the
  // operator types a bootstrap host of their own.
  useEffect(() => {
    if (!hostTouched) setBrokerHost(suggestedHost);
  }, [hostTouched, suggestedHost]);

  const useDemoBroker = () => {
    setBrokerHost(suggestedHost);
    setHostTouched(false);
    setBrokerPort(DEMO_KAFKA_PORT);
  };

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
          <Metric label="Topic listing" value={topicsEnabled ? "LIVE" : "CLI ONLY"} />
          <div className="space-y-1 sm:col-span-2 lg:col-span-4">
            {rows.length === 0 ? (
              <p className="text-[11.5px] text-warning">
                No Kafka broker Service was reported in{" "}
                <span className="mono">{scope.namespace || "this namespace"}</span>, so there are no
                topics to list. Services whose name or labels contain <span className="mono">kafka</span>{" "}
                are reported. The bundled demo broker lives in namespace{" "}
                <span className="mono">default</span> — switch the namespace picker, or point the{" "}
                <span className="mono">Topics</span> tab at{" "}
                <span className="mono">
                  {suggestedHost}:{DEMO_KAFKA_PORT}
                </span>
                .
              </p>
            ) : null}
            <p className="text-[11.5px] text-text-muted">
              The <span className="mono">Topics</span> tab lists topic names and partitions with a
              single read-only Metadata request when the backend runs with{" "}
              <span className="mono">DSWEB_ENABLE_KAFKA_TOPICS=1</span>. Consumer-group and offset
              detail still needs the engine console: run <span className="mono">{engineCmd}</span> and
              choose <span className="mono">Kafka → List topics</span>.
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
          <div className="space-y-3">
            <Card>
              <CardHeader>
                <CardTitle>List topics</CardTitle>
                <Badge tone={topicsEnabled ? "info" : "unknown"}>
                  {topicsEnabled ? "ENABLED" : "DISABLED"}
                </Badge>
              </CardHeader>
              <CardBody className="space-y-2">
                {!topicsEnabled ? (
                  <p className="text-[12.5px] text-warning">
                    {consoleStatus.data?.data.reason ?? "checking the topic-listing status…"} — restart
                    the backend with <span className="mono">DSWEB_ENABLE_KAFKA_TOPICS=1</span> to turn
                    it on.
                  </p>
                ) : null}
                <p className="text-[11.5px] text-text-muted">
                  A single read-only Kafka <span className="mono">Metadata</span> request against the
                  bootstrap address. No credentials, no consumer groups, no offsets, no writes.
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <label className="block">
                    <span className="text-[10.5px] uppercase tracking-wide text-text-faint">
                      Bootstrap host
                    </span>
                    <Input
                      aria-label="Bootstrap host"
                      className="mt-1 w-[220px]"
                      value={brokerHost}
                      onChange={(event) => {
                        setHostTouched(true);
                        setBrokerHost(event.target.value);
                      }}
                    />
                  </label>
                  <label className="block">
                    <span className="text-[10.5px] uppercase tracking-wide text-text-faint">
                      Port
                    </span>
                    <Input
                      aria-label="Bootstrap port"
                      className="mt-1 w-[110px]"
                      value={brokerPort}
                      onChange={(event) => setBrokerPort(event.target.value)}
                    />
                  </label>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!topicsEnabled || listTopics.isPending}
                    onClick={() => listTopics.mutate({ host: brokerHost, port: Number(brokerPort) })}
                  >
                    List topics
                  </Button>
                  <Button variant="outline" size="sm" onClick={useDemoBroker}>
                    Use demo broker
                  </Button>
                  {listTopics.isPending ? (
                    <span className="text-[11.5px] text-text-muted">asking the broker…</span>
                  ) : null}
                </div>
                <p className="text-[11px] text-text-faint">
                  Host prefills with the cluster node address, because the bundled demo broker is a
                  NodePort and answers on a node — not on <span className="mono">127.0.0.1</span>. The
                  demo endpoint is{" "}
                  <span className="mono">
                    {suggestedHost}:{DEMO_KAFKA_PORT}
                  </span>{" "}
                  (namespace <span className="mono">default</span>).
                </p>
                {listTopics.isError ? (
                  <p className="text-[12px] text-critical">{(listTopics.error as Error).message}</p>
                ) : null}
              </CardBody>
            </Card>

            {listing ? (
              <Card>
                <CardHeader>
                  <CardTitle>Topics</CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{listing.topics.length} topics</Badge>
                    {listing.truncated ? <Badge tone="warning">truncated</Badge> : null}
                    <span className="mono text-[11px] text-text-muted">{listing.bootstrap}</span>
                  </div>
                </CardHeader>
                <CardBody className="p-0">
                  {listing.topics.length === 0 ? (
                    <p className="p-3 text-[12.5px] text-text-muted">
                      The broker is reachable but reports no topics.
                    </p>
                  ) : (
                    <table className="w-full border-collapse text-[12px]">
                      <thead className="bg-panel-2">
                        <tr>
                          <th scope="col" className="px-3 py-1.5 text-left text-[10.5px] uppercase tracking-wide text-text-muted">
                            Topic
                          </th>
                          <th scope="col" className="px-3 py-1.5 text-left text-[10.5px] uppercase tracking-wide text-text-muted">
                            Partitions
                          </th>
                          <th scope="col" className="px-3 py-1.5 text-left text-[10.5px] uppercase tracking-wide text-text-muted">
                            Kind
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {listing.topics.map((topic) => (
                          <tr key={topic.name} className="border-b border-border/50">
                            <td className="mono px-3 py-1">{topic.name}</td>
                            <td className="mono px-3 py-1">{topic.partitions}</td>
                            <td className="px-3 py-1">
                              <Badge tone={topic.internal ? "unknown" : "ok"}>
                                {topic.internal ? "internal" : "user"}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <div className="border-t border-border px-3 py-2 text-[11.5px] text-text-muted">
                    Brokers:{" "}
                    <span className="mono">{listing.brokers.join(", ") || "none reported"}</span>
                  </div>
                </CardBody>
              </Card>
            ) : null}

            <Card>
              <CardHeader>
                <CardTitle>Bootstrap candidates</CardTitle>
                <Badge tone="neutral">{rows.length} services</Badge>
              </CardHeader>
              <CardBody className="space-y-2">
                {rows.length === 0 ? (
                  <EmptyState
                    title="No broker discovered"
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
                            ? "in-cluster: kafka-topics.sh --bootstrap-server " +
                              row.bootstrap +
                              " --list"
                            : "no usable port reported"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-[11.5px] text-text-muted">
                  Topic, partition and consumer-group detail is available through the opt-in listing
                  above or the engine console; nothing is read unless you ask for it.
                </p>
              </CardBody>
            </Card>
          </div>
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

