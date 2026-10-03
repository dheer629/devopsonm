import { useMemo } from "react";

import { useDoctor, useEtDp, useDatabase, useKafka } from "@/api/queries";
import { ErrorState, Freshness, LoadingRows, PageHeader, RawView } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { useApp } from "@/state/AppContext";

export type ReportKind = "etdp" | "database" | "kafka" | "health";

const META: Record<ReportKind, { title: string; subtitle: string }> = {
  etdp: {
    title: "ETDP Platform",
    subtitle: "Recognisable platform workloads grouped from engine evidence.",
  },
  database: {
    title: "Database",
    subtitle: "Read-only PostgreSQL / generic DB discovery. Credentials are never stored.",
  },
  kafka: {
    title: "Kafka",
    subtitle: "Bootstrap endpoints, TLS configuration metadata and connectivity.",
  },
  health: {
    title: "Smart Health",
    subtitle: "Evidence-first health report. Interpretation never hides the raw evidence.",
  },
};

export function ReportPage({ kind }: { kind: ReportKind }) {
  const { scope } = useApp();
  const etdp = useEtDp(scope, kind === "etdp");
  const database = useDatabase(scope, kind === "database");
  const kafka = useKafka(scope, kind === "kafka");
  const health = useDoctor(scope, kind === "health");

  const active =
    kind === "etdp" ? etdp : kind === "database" ? database : kind === "kafka" ? kafka : health;
  const meta = META[kind];

  const lines = useMemo(
    () => (active.data?.envelope.data ?? "").split("\n").filter((line) => line.trim() !== ""),
    [active.data],
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title={meta.title}
        subtitle={meta.subtitle}
        actions={
          <div className="flex items-center gap-2">
            {kind === "database" ? <Badge tone="warning">read-only queries only</Badge> : null}
            {kind === "kafka" ? <Badge tone="warning">no credentials exposed</Badge> : null}
            {active.data ? <Freshness envelope={active.data.envelope} /> : null}
          </div>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Report</CardTitle>
          <Badge tone="neutral">{lines.length} lines</Badge>
        </CardHeader>
        <CardBody className="p-0">
          {active.isLoading ? <LoadingRows /> : null}
          {active.data?.envelope.errors.length ? (
            <div className="p-3">
              <ErrorState envelope={active.data.envelope} onRetry={() => void active.refetch()} />
            </div>
          ) : null}
          {lines.length > 0 ? (
            <pre className="mono max-h-[520px] overflow-auto whitespace-pre-wrap bg-bg-elevated p-3 text-[11.5px] text-text">
              {lines.join("\n")}
            </pre>
          ) : null}
          {!active.isLoading && lines.length === 0 && !active.data?.envelope.errors.length ? (
            <p className="p-3 text-[12.5px] text-text-muted">
              No data was reported for this scope. Optional capability missing or nothing matched.
            </p>
          ) : null}
        </CardBody>
      </Card>

      <RawView raw={active.data?.raw} />
    </div>
  );
}
