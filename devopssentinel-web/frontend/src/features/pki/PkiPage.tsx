import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";

import { useCertificates } from "@/api/queries";
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
import type { Certificate } from "@/types";

export function PkiPage() {
  const { scope, setSelection } = useApp();
  const certificates = useCertificates(scope);

  const rows = useMemo(
    () =>
      [...(certificates.data?.envelope.data ?? [])].sort(
        (a, b) => (a.days ?? Number.MAX_SAFE_INTEGER) - (b.days ?? Number.MAX_SAFE_INTEGER),
      ),
    [certificates.data],
  );

  const summary = useMemo(() => {
    const all = certificates.data?.envelope.data ?? [];
    const bucket = (min: number, max: number) =>
      all.filter((c) => c.days !== null && c.days >= min && c.days < max).length;
    return {
      total: all.length,
      healthy: all.filter((c) => c.days === null || c.days > 90).length,
      d90: bucket(61, 91),
      d60: bucket(31, 61),
      d30: bucket(8, 31),
      d7: bucket(0, 8),
      expired: all.filter((c) => c.days !== null && c.days < 0).length,
      unknown: all.filter((c) => c.days === null).length,
    };
  }, [certificates.data]);

  const columns = useMemo<ColumnDef<Certificate, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Certificate",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "namespace", header: "Namespace" },
      { accessorKey: "cn", header: "CN" },
      { accessorKey: "issuer", header: "Issuer" },
      {
        accessorKey: "expiry",
        header: "Expiry",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "days",
        header: "Days",
        cell: (info) => (
          <span className="mono">{info.getValue() === null ? "—" : String(info.getValue())}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
      },
      { accessorKey: "consumers", header: "Consumers" },
    ],
    [],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="PKI / TLS Command Center"
        subtitle={`${summary.total} certificates · sorted by nearest expiry`}
        actions={certificates.data ? <Freshness envelope={certificates.data.envelope} /> : null}
      />

      {certificates.data ? <PartialBanner envelope={certificates.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Expiry posture</CardTitle>
        </CardHeader>
        <CardBody className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          <Metric label="Total" value={summary.total} />
          <Metric label="Healthy" value={summary.healthy} tone="ok" />
          <Metric label="≤90 days" value={summary.d90} tone="info" />
          <Metric label="≤60 days" value={summary.d60} tone="info" />
          <Metric label="≤30 days" value={summary.d30} tone="warning" />
          <Metric label="≤7 days" value={summary.d7} tone="critical" />
          <Metric label="Expired" value={summary.expired} tone="critical" />
          <Metric label="Unknown" value={summary.unknown} tone="unknown" />
        </CardBody>
      </Card>

      <Card>
        <CardBody className="p-0">
          {certificates.isLoading ? <LoadingRows /> : null}
          {certificates.data?.envelope.errors.length ? (
            <div className="p-3">
              <ErrorState
                envelope={certificates.data.envelope}
                onRetry={() => void certificates.refetch()}
              />
            </div>
          ) : null}
          {certificates.data && !certificates.data.envelope.errors.length ? (
            <DataTable
              data={rows}
              columns={columns}
              exportName="devopssentinel-certificates"
              emptyMessage="No certificates were reported for this namespace."
              onRowClick={(cert) => setSelection({ kind: "Secret", name: cert.name })}
            />
          ) : null}
        </CardBody>
      </Card>

      <p className="text-[11px] text-text-muted">
        Private keys, tls.key and Secret payloads are never requested, transported or displayed. Live
        TLS comparison remains available only in the engine's interactive console.
      </p>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "ok" | "info" | "warning" | "critical" | "unknown";
}) {
  const toneClass: Record<string, string> = {
    neutral: "text-text",
    ok: "text-success",
    info: "text-info",
    warning: "text-warning",
    critical: "text-critical",
    unknown: "text-unknown",
  };
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className={`mono text-[16px] ${toneClass[tone]}`}>{value}</div>
    </div>
  );
}
