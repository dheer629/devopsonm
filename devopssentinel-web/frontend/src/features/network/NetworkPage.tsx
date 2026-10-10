import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { useEndpointGaps, useEndpoints, usePods, usePodPolicies, useServices } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  EmptyState,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ServiceDetail } from "@/features/network/ServiceDetail";
import { useApp } from "@/state/AppContext";
import type { ServiceResource } from "@/types";

export function NetworkPage() {
  const { scope, setSelection } = useApp();
  const services = useServices(scope);
  const gaps = useEndpointGaps(scope);
  const endpoints = useEndpoints(scope);
  const pods = usePods(scope);
  const [selected, setSelected] = useState<string | null>(null);
  const [policyPod, setPolicyPod] = useState("");
  const policies = usePodPolicies(scope, policyPod, Boolean(policyPod));

  const columns = useMemo<ColumnDef<ServiceResource, unknown>[]>(
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
        accessorKey: "external_ip",
        header: "External IP",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "ready_endpoints",
        header: "Ready",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      {
        accessorKey: "not_ready_endpoints",
        header: "Not ready",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      {
        accessorKey: "ports",
        header: "Ports",
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

  const gapRows = gaps.data?.envelope.data ?? [];

  return (
    <div className="space-y-3">
      <PageHeader
        title="Network Operations"
        subtitle={`${services.data?.envelope.data.length ?? 0} services · ${gapRows.length} endpoint gaps`}
        actions={services.data ? <Freshness envelope={services.data.envelope} /> : null}
      />

      {services.data ? <PartialBanner envelope={services.data.envelope} /> : null}

      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-3">
          <Tabs defaultValue="services">
        <TabsList>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="endpoints">EndpointSlices</TabsTrigger>
          <TabsTrigger value="gaps">Endpoint gaps</TabsTrigger>
          <TabsTrigger value="policies">Network policies</TabsTrigger>
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
                  data={services.data.envelope.data}
                  columns={columns}
                  exportName="devopssentinel-services"
                  emptyMessage="No services were reported for this namespace."
                  onRowClick={(svc) => {
                    setSelected(svc.name);
                    setSelection({ kind: "Service", name: svc.name });
                  }}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="endpoints">
          <Card>
            <CardHeader>
              <CardTitle>EndpointSlices by Service</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              {endpoints.isLoading ? <LoadingRows /> : null}
              {endpoints.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState
                    envelope={endpoints.data.envelope}
                    onRetry={() => void endpoints.refetch()}
                  />
                </div>
              ) : null}
              {endpoints.data && !endpoints.data.envelope.errors.length ? (
                <DataTable
                  data={endpoints.data.envelope.data}
                  columns={columns}
                  exportName="devopssentinel-endpointslices"
                  emptyMessage="No Service endpoint data was reported for this namespace."
                  onRowClick={(svc) => {
                    setSelected(svc.name);
                    setSelection({ kind: "Service", name: svc.name });
                  }}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="gaps">
          <Card>
            <CardHeader>
              <CardTitle>Services with zero ready endpoints</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              {gapRows.length === 0 ? (
                <EmptyState
                  title="No endpoint gaps found"
                  detail={`${services.data?.envelope.data.length ?? 0} services checked; every service reported at least one ready endpoint.`}
                />
              ) : (
                <DataTable
                  data={gapRows}
                  columns={columns}
                  exportName="devopssentinel-endpoint-gaps"
                  emptyMessage="No endpoint gaps."
                  onRowClick={(svc) => setSelection({ kind: "Service", name: svc.name })}
                />
              )}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="policies">
          <Card>
            <CardHeader>
              <CardTitle>NetworkPolicy isolation</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <p className="text-[12px] text-text-muted">
                Pick a Pod to see which NetworkPolicies select it. This is a{" "}
                <strong>configuration</strong> view: it reports which policies match the Pod, not
                whether traffic is actually permitted at runtime.
              </p>
              <Select value={policyPod} onValueChange={setPolicyPod}>
                <SelectTrigger className="w-72" aria-label="Pod for network policy check">
                  <SelectValue placeholder="Select a Pod" />
                </SelectTrigger>
                <SelectContent>
                  {(pods.data?.envelope.data ?? []).map((pod) => (
                    <SelectItem key={`${pod.namespace}/${pod.name}`} value={pod.name}>
                      {pod.namespace}/{pod.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {!policyPod ? (
                <EmptyState
                  title="No Pod selected"
                  detail="Choose a Pod above to list the NetworkPolicies that select it."
                />
              ) : null}
              {policyPod && policies.isLoading ? <LoadingRows rows={3} /> : null}
              {policyPod && policies.data ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={policies.data.envelope.data?.isolated ? "warning" : "ok"}>
                      {policies.data.envelope.data?.isolated
                        ? "POLICIES SELECT THIS POD"
                        : "NO SELECTING POLICY OBSERVED"}
                    </Badge>
                    <span className="text-[11.5px] text-text-muted">
                      {(policies.data.envelope.data?.selectingPolicies ?? []).length} selecting
                      {(policies.data.envelope.data?.selectingPolicies ?? []).length === 1
                        ? " policy"
                        : " policies"}
                    </span>
                  </div>
                  {(policies.data.envelope.data?.selectingPolicies ?? []).length > 0 ? (
                    <ul className="space-y-0.5">
                      {(policies.data.envelope.data?.selectingPolicies ?? []).map((item) => (
                        <li key={item} className="mono text-[12px] text-text">
                          {item}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="text-[11px] text-text-faint">
                    {policies.data.envelope.data?.note}
                  </p>
                </>
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>
      </Tabs>

          <Card>
            <CardHeader>
              <CardTitle>Port path analyzer</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              <p className="text-[12px] text-text-muted">
                Trace{" "}
                <span className="mono">Ingress → Service → EndpointSlice → Pod</span> for one Service.
                Mismatches are reported as a{" "}
                <strong>configuration observation</strong> unless the engine provides evidence of an
                actual connectivity failure.
              </p>
              <Select value={selected ?? ""} onValueChange={(value) => setSelected(value)}>
                <SelectTrigger className="w-72" aria-label="Service for port path">
                  <SelectValue placeholder="Select a Service to trace" />
                </SelectTrigger>
                <SelectContent>
                  {(services.data?.envelope.data ?? []).map((svc) => (
                    <SelectItem key={`${svc.namespace}/${svc.name}`} value={svc.name}>
                      {svc.namespace}/{svc.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardBody>
          </Card>
        </div>
        {selected ? (
          <ServiceDetail name={selected} onClose={() => setSelected(null)} />
        ) : null}
      </div>
    </div>
  );
}
