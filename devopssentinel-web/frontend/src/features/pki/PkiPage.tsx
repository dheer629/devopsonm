import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import {
  useCertificateDuplicates,
  useCertificateExpiry,
  useCertificateIssuers,
  useCertificates,
  useSecrets,
} from "@/api/queries";
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
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CertificateDetail } from "@/features/pki/CertificateDetail";
import { useApp } from "@/state/AppContext";
import type { Certificate, SecretRecord } from "@/types";

export function PkiPage() {
  const { scope, setSelection } = useApp();
  const certificates = useCertificates(scope);
  const secrets = useSecrets(scope);
  const issuers = useCertificateIssuers(scope);
  const duplicates = useCertificateDuplicates(scope);
  const engineExpiry = useCertificateExpiry(scope);
  const [tab, setTab] = useState("certificates");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      [...(certificates.data?.envelope.data ?? [])].sort(
        (a, b) => (a.days ?? Number.MAX_SAFE_INTEGER) - (b.days ?? Number.MAX_SAFE_INTEGER),
      ),
    [certificates.data],
  );

  const secretRows = useMemo(
    () =>
      [...(secrets.data?.envelope.data ?? [])].sort(
        (a, b) => (a.days ?? Number.MAX_SAFE_INTEGER) - (b.days ?? Number.MAX_SAFE_INTEGER),
      ),
    [secrets.data],
  );

  // Expiry posture. The engine's own `--cert-expiry` audit applies the
  // thresholds the CLI uses (CRITICAL<=7d, WARNING<=30d, ATTENTION<=60d), so it
  // is the source of truth. The inventory-derived counts are only a fallback
  // for when that report is unavailable -- the GUI never invents a threshold
  // the engine did not state (spec sections 66, 286, 290).
  const expirySource = engineExpiry.data?.envelope.data ?? [];
  const usingEngineThresholds = expirySource.length > 0;

  const summary = useMemo(() => {
    const all = usingEngineThresholds ? expirySource : (certificates.data?.envelope.data ?? []);
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
  }, [certificates.data, expirySource, usingEngineThresholds]);

  const secretSummary = useMemo(() => {
    const all = secrets.data?.envelope.data ?? [];
    return {
      total: all.length,
      tls: all.filter((s) => s.is_tls).length,
      expiring: all.filter((s) => s.days !== null && s.days <= 30).length,
    };
  }, [secrets.data]);

  // Issuers: prefer the engine's own issuer endpoint, falling back to the
  // issuers already present in the inventory so the two never disagree silently.
  const issuerList = useMemo(() => {
    const fromEngine = issuers.data?.envelope.data ?? [];
    if (fromEngine.length > 0) return [...fromEngine].sort();
    return [
      ...new Set(
        (certificates.data?.envelope.data ?? []).map((cert) => cert.issuer).filter(Boolean),
      ),
    ].sort();
  }, [issuers.data, certificates.data]);

  // Duplicate subjects: the engine groups certificates that share a CN.
  const duplicateGroups = useMemo(() => {
    const grouped = duplicates.data?.envelope.data ?? {};
    return Object.entries(grouped)
      .map(([cn, names]) => ({ cn, names: [...names].sort() }))
      .sort((a, b) => a.cn.localeCompare(b.cn));
  }, [duplicates.data]);

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
      {
        accessorKey: "serial",
        header: "Serial",
        cell: (info) => (
          <span className="mono text-text-muted">{truncate(String(info.getValue() || ""), 16)}</span>
        ),
      },
      {
        accessorKey: "san",
        header: "SAN",
        cell: (info) => (
          <span className="mono text-text-muted">{String(info.getValue() || "—")}</span>
        ),
      },
      { accessorKey: "consumers", header: "Consumers" },
    ],
    [],
  );

  const secretColumns = useMemo<ColumnDef<SecretRecord, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Secret",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "type", header: "Type" },
      {
        accessorKey: "created",
        header: "Created",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "keys",
        header: "Keys",
        cell: (info) => (
          <span className="mono text-text-muted">{String(info.getValue() || "—")}</span>
        ),
      },
      {
        accessorKey: "key_count",
        header: "Key count",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      {
        accessorKey: "expires",
        header: "Expires",
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
    ],
    [],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="PKI / TLS Command Center"
        subtitle={`${summary.total} certificates · ${secretSummary.tls} TLS secrets · sorted by nearest expiry`}
        actions={certificates.data ? <Freshness envelope={certificates.data.envelope} /> : null}
      />

      {certificates.data ? <PartialBanner envelope={certificates.data.envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Expiry posture</CardTitle>
          <Badge tone={usingEngineThresholds ? "ok" : "warning"}>
            {usingEngineThresholds
              ? "engine thresholds"
              : "inventory fallback — engine expiry audit unavailable"}
          </Badge>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-8">
            <Metric label="Total" value={summary.total} />
            <Metric label="Healthy" value={summary.healthy} tone="ok" />
            <Metric label="≤90 days" value={summary.d90} tone="info" />
            <Metric label="≤60 days" value={summary.d60} tone="info" />
            <Metric label="≤30 days" value={summary.d30} tone="warning" />
            <Metric label="≤7 days" value={summary.d7} tone="critical" />
            <Metric label="Expired" value={summary.expired} tone="critical" />
            <Metric label="Unknown" value={summary.unknown} tone="unknown" />
          </div>

          {/* Issuers and duplicate CNs come from the engine's own certificate
              report, so they agree with the inventory above (spec section 66). */}
          <div className="grid grid-cols-1 gap-3 border-t border-border pt-3 md:grid-cols-2">
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Issuers ({issuerList.length})
              </h3>
              {issuerList.length === 0 ? (
                <p className="text-[12px] text-text-muted">None reported.</p>
              ) : (
                <ul className="mt-1 flex flex-wrap gap-1">
                  {issuerList.map((issuer) => (
                    <li
                      key={issuer}
                      className="mono rounded-sm border border-border px-1.5 py-0.5 text-[11px] text-text-muted"
                    >
                      {issuer}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Duplicate subjects ({duplicateGroups.length})
              </h3>
              {duplicateGroups.length === 0 ? (
                <p className="text-[12px] text-text-muted">
                  No two certificates share a subject in this scope.
                </p>
              ) : (
                <ul className="mt-1 space-y-0.5">
                  {duplicateGroups.map((group) => (
                    <li key={group.cn} className="text-[11.5px]">
                      <span className="mono text-text">{group.cn}</span>{" "}
                      <span className="text-text-muted">→ {group.names.join(", ")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </CardBody>
      </Card>

      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="certificates">Certificates ({summary.total})</TabsTrigger>
          <TabsTrigger value="secrets">
            Secrets ({secretSummary.total})
            {secretSummary.expiring > 0 ? ` · ${secretSummary.expiring} expiring` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="certificates">
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
                  onRowClick={(cert) => {
                    setSelected(cert.name);
                    setSelection({ kind: "Secret", name: cert.name });
                  }}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="secrets">
          <Card>
            <CardBody className="p-0">
              {secrets.isLoading ? <LoadingRows /> : null}
              {secrets.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState
                    envelope={secrets.data.envelope}
                    onRetry={() => void secrets.refetch()}
                  />
                </div>
              ) : null}
              {secrets.data && !secrets.data.envelope.errors.length ? (
                <DataTable
                  data={secretRows}
                  columns={secretColumns}
                  exportName="devopssentinel-secrets"
                  emptyMessage="No Secrets were reported for this namespace."
                  onRowClick={(secret) => setSelection({ kind: "Secret", name: secret.name })}
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>
          </Tabs>
        </div>
        {selected ? (
          <CertificateDetail name={selected} onClose={() => setSelected(null)} />
        ) : null}
      </div>

      <p className="text-[11px] text-text-muted">
        Secret expiry is the X.509 validity of the certificate carried by a{" "}
        <span className="mono">kubernetes.io/tls</span> Secret. Private keys, tls.key and Secret
        payloads are never requested, transported or displayed. Live TLS comparison remains available
        only in the engine's interactive console.
      </p>
    </div>
  );
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value || "—";
  return `${value.slice(0, max)}…`;
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
