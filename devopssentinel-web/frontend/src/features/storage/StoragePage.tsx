import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { useStorage } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { useApp } from "@/state/AppContext";
import type { PVCResource } from "@/types";

export function StoragePage() {
  const { scope, setSelection } = useApp();
  const storage = useStorage(scope);

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

  return (
    <div className="space-y-3">
      <PageHeader
        title="Storage Center"
        subtitle={`${bound} / ${total} PVCs bound`}
        actions={storage.data ? <Freshness envelope={storage.data.envelope} /> : null}
      />

      {storage.data ? <PartialBanner envelope={storage.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>PersistentVolumeClaims</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {storage.isLoading ? <LoadingRows /> : null}
          {storage.data?.envelope.errors.length ? (
            <div className="p-3">
              <ErrorState envelope={storage.data.envelope} onRetry={() => void storage.refetch()} />
            </div>
          ) : null}
          {storage.data && !storage.data.envelope.errors.length ? (
            <DataTable
              data={rows}
              columns={columns}
              exportName="devopssentinel-storage"
              emptyMessage="No PersistentVolumeClaims were reported for this namespace."
              onRowClick={(pvc) => setSelection({ kind: "PersistentVolumeClaim", name: pvc.name })}
            />
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>PVC dependency chain</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-[12px] text-text-muted">
            Select a PVC to trace{" "}
            <span className="mono">
              StatefulSet → Pod → PVC → PV → StorageClass
            </span>{" "}
            in the context inspector, including mount paths and consumers reported by the engine.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
