import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { useMountWarnings, useStorage } from "@/api/queries";
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
import { PvcDetail } from "@/features/storage/PvcDetail";
import { useApp } from "@/state/AppContext";
import type { PVCResource } from "@/types";

export function StoragePage() {
  const { scope, setSelection } = useApp();
  const storage = useStorage(scope);
  const mountWarnings = useMountWarnings(scope);
  const [selected, setSelected] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      [...(storage.data?.envelope.data ?? [])].sort((a, b) =>
        a.severity === b.severity ? 0 : a.severity === "OK" ? 1 : -1,
      ),
    [storage.data],
  );

  const columns = useMemo<ColumnDef<PVCResource, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "PVC",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "namespace", header: "Namespace" },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} label={String(info.getValue())} />,
      },
      { accessorKey: "capacity", header: "Capacity" },
      { accessorKey: "access_modes", header: "Access modes" },
      { accessorKey: "storage_class", header: "StorageClass" },
      {
        accessorKey: "volume",
        header: "Volume",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "consumers",
        header: "Consumers",
        cell: (info) => {
          const list = (info.getValue() as string[]) ?? [];
          return (
            <span className="mono" title={list.join(", ")}>
              {list.length ? list.join(", ") : "—"}
            </span>
          );
        },
      },
    ],
    [],
  );

  const bound = (storage.data?.envelope.data ?? []).filter((p) => p.severity === "OK").length;
  const total = storage.data?.envelope.data.length ?? 0;

  // Mount warnings come from the engine, split into claims it did not mark OK
  // and claims with no observed consumer (spec section 86).
  const warnings = mountWarnings.data?.envelope.data?.warnings ?? [];
  const unconsumed = mountWarnings.data?.envelope.data?.unconsumed ?? [];

  const openRow = (pvc: PVCResource) => {
    setSelected(pvc.name);
    setSelection({ kind: "PersistentVolumeClaim", name: pvc.name });
  };

  return (
    <div className="space-y-3">
      <PageHeader
        title="Storage Center"
        subtitle={`${bound} / ${total} PVCs bound`}
        actions={storage.data ? <Freshness envelope={storage.data.envelope} /> : null}
      />

      {storage.data ? <PartialBanner envelope={storage.data.envelope} /> : null}

      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Tabs defaultValue="claims">
            <TabsList>
              <TabsTrigger value="claims">Claims ({total})</TabsTrigger>
              <TabsTrigger value="warnings">
                Mount warnings ({warnings.length + unconsumed.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="claims">
              <Card>
                <CardHeader>
                  <CardTitle>PersistentVolumeClaims</CardTitle>
                </CardHeader>
                <CardBody className="p-0">
                  {storage.isLoading ? <LoadingRows /> : null}
                  {storage.data?.envelope.errors.length ? (
                    <div className="p-3">
                      <ErrorState
                        envelope={storage.data.envelope}
                        onRetry={() => void storage.refetch()}
                      />
                    </div>
                  ) : null}
                  {storage.data && !storage.data.envelope.errors.length ? (
                    <DataTable
                      data={rows}
                      columns={columns}
                      exportName="devopssentinel-storage"
                      emptyMessage="No PersistentVolumeClaims were reported for this namespace."
                      onRowClick={openRow}
                    />
                  ) : null}
                </CardBody>
              </Card>
            </TabsContent>

            <TabsContent value="warnings">
              <div className="space-y-3">
                <Card>
                  <CardHeader>
                    <CardTitle>Claims the engine did not mark OK ({warnings.length})</CardTitle>
                  </CardHeader>
                  <CardBody className="p-0">
                    {mountWarnings.isLoading ? <LoadingRows /> : null}
                    {!mountWarnings.isLoading && warnings.length === 0 ? (
                      <EmptyState
                        title="No unbound or unhealthy claims"
                        detail={`${total} claims checked; the engine marked every one OK.`}
                      />
                    ) : (
                      <DataTable
                        data={warnings}
                        columns={columns}
                        exportName="devopssentinel-storage-warnings"
                        emptyMessage="No mount warnings."
                        onRowClick={openRow}
                      />
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Claims with no observed consumer ({unconsumed.length})</CardTitle>
                  </CardHeader>
                  <CardBody className="p-0">
                    {!mountWarnings.isLoading && unconsumed.length === 0 ? (
                      <EmptyState
                        title="Every claim has a consumer"
                        detail="The engine's dependency report shows at least one workload mounting each claim."
                      />
                    ) : (
                      <DataTable
                        data={unconsumed}
                        columns={columns}
                        exportName="devopssentinel-storage-unconsumed"
                        emptyMessage="No unconsumed claims."
                        onRowClick={openRow}
                      />
                    )}
                  </CardBody>
                </Card>

                <p className="text-[11px] text-text-muted">
                  An unconsumed claim is a real signal: its provisioned volume still costs money. It
                  means no consumer was found in the engine&apos;s dependency report, not that none
                  exists.
                </p>
              </div>
            </TabsContent>
          </Tabs>
        </div>
        {selected ? <PvcDetail name={selected} onClose={() => setSelected(null)} /> : null}
      </div>
    </div>
  );
}
