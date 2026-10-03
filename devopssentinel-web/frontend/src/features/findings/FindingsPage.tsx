import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { useFindings } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  ConfidenceTag,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { severityRank } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { Finding } from "@/types";

export function FindingsPage() {
  const { scope, setSelection } = useApp();
  const findings = useFindings(scope);
  const [domain, setDomain] = useState("ALL");
  const [severity, setSeverity] = useState("ALL");

  const rows = useMemo(() => {
    const all = [...(findings.data?.envelope.data ?? [])].sort(
      (a, b) => severityRank(a.severity) - severityRank(b.severity),
    );
    return all.filter(
      (row) =>
        (domain === "ALL" || row.domain === domain) &&
        (severity === "ALL" || row.severity === severity),
    );
  }, [findings.data, domain, severity]);

  const domains = useMemo(
    () => Array.from(new Set((findings.data?.envelope.data ?? []).map((f) => f.domain))).sort(),
    [findings.data],
  );

  const columns = useMemo<ColumnDef<Finding, unknown>[]>(
    () => [
      { accessorKey: "id", header: "ID", cell: (info) => <span className="mono">{String(info.getValue())}</span> },
      {
        accessorKey: "severity",
        header: "Severity",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
        sortingFn: (a, b) => severityRank(a.original.severity) - severityRank(b.original.severity),
      },
      { accessorKey: "lifecycle", header: "Lifecycle" },
      { accessorKey: "domain", header: "Domain" },
      {
        accessorKey: "resource",
        header: "Resource",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "finding", header: "Finding" },
      {
        accessorKey: "confidence",
        header: "Confidence",
        cell: (info) => <ConfidenceTag confidence={String(info.getValue())} />,
      },
    ],
    [],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="Findings Center"
        subtitle={`${rows.length} findings shown of ${findings.data?.envelope.data.length ?? 0} collected`}
        actions={findings.data ? <Freshness envelope={findings.data.envelope} /> : null}
      />

      {findings.data ? <PartialBanner envelope={findings.data.envelope} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-44">
          <Select value={domain} onValueChange={setDomain}>
            <SelectTrigger aria-label="Filter by domain">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All domains</SelectItem>
              {domains.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger aria-label="Filter by severity">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["ALL", "CRITICAL", "FAILED", "WARNING", "NOTICE", "UNKNOWN"].map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={() => void findings.refetch()}>
          Refresh
        </Button>
      </div>

      <Card>
        <CardBody className="p-0">
          {findings.isLoading ? <LoadingRows /> : null}
          {findings.data?.envelope.errors.length ? (
            <div className="p-3">
              <ErrorState envelope={findings.data.envelope} onRetry={() => void findings.refetch()} />
            </div>
          ) : null}
          {findings.data && !findings.data.envelope.errors.length ? (
            <DataTable
              data={rows}
              columns={columns}
              exportName="devopssentinel-findings"
              emptyMessage="No findings match the current filters."
              onRowClick={(finding) => {
                const [kind, name] = finding.resource.split("/");
                if (kind && name) setSelection({ kind, name });
              }}
            />
          ) : null}
        </CardBody>
      </Card>

      <p className="text-[11px] text-text-muted">
        Findings describe observations and evidence. Nothing here is labelled a root cause unless
        causality is explicitly proven by the engine.
      </p>
    </div>
  );
}
