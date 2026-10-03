import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { useEndpointGaps, useServices } from "@/api/queries";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApp } from "@/state/AppContext";
import type { ServiceResource } from "@/types";

export function NetworkPage() {
  const { scope, setSelection } = useApp();
  const services = useServices(scope);
  const gaps = useEndpointGaps(scope);

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

      <Tabs defaultValue="services">
        <TabsList>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="gaps">Endpoint gaps</TabsTrigger>
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
                  onRowClick={(svc) => setSelection({ kind: "Service", name: svc.name })}
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
      </Tabs>

      <Card>
        <CardHeader>
          <CardTitle>Port path analyzer</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-[12px] text-text-muted">
            Open a service in the inspector to trace Ingress → Service → targetPort → container port.
            Mismatches are reported as a <strong>configuration observation</strong> unless the engine
            provides evidence of an actual connectivity failure.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
