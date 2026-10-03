import { Link } from "react-router-dom";

import {
  useCertificates,
  useEndpointGaps,
  useFindings,
  useGitOps,
  usePods,
  useStorage,
  useWorkloads,
} from "@/api/queries";
import { Freshness, PageHeader, PartialBanner, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { severityOf, severityRank, type Severity } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { Envelope } from "@/types";

function bucket<T>(items: T[], pick: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = severityOf(pick(item));
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

export function DashboardPage() {
  const { scope } = useApp();
  const workloads = useWorkloads(scope);
  const pods = usePods(scope);
  const findings = useFindings(scope);
  const gitops = useGitOps(scope);
  const certificates = useCertificates(scope);
  const gaps = useEndpointGaps(scope);
  const storage = useStorage(scope);

  const workloadRows = workloads.data?.envelope.data ?? [];
  const podRows = pods.data?.envelope.data ?? [];
  const findingRows = [...(findings.data?.envelope.data ?? [])].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity),
  );
  const gitopsRows = gitops.data?.envelope.data ?? [];
  const certRows = certificates.data?.envelope.data ?? [];
  const gapRows = gaps.data?.envelope.data ?? [];
  const pvcRows = storage.data?.envelope.data ?? [];

  const workloadBuckets = bucket(workloadRows, (w) => w.status);
  const podBuckets = bucket(podRows, (p) => p.status);
  const gitopsFailures = gitopsRows.filter((g) => g.ready === false || g.status === "CRITICAL");
  const certWarn = certRows.filter((c) => c.days !== null && c.days <= 30);
  const pvcPending = pvcRows.filter((p) => p.severity !== "OK");

  const attentionAll: { label: string; severity: Severity; count: number; to: string }[] = [
    {
      label: "unhealthy workloads",
      severity: "CRITICAL",
      count: (workloadBuckets.CRITICAL ?? 0) + (podBuckets.CRITICAL ?? 0),
      to: "/workloads",
    },
    {
      label: "GitOps objects not ready",
      severity: "FAILED",
      count: gitopsFailures.length,
      to: "/gitops",
    },
    { label: "certificates ≤30 days", severity: "WARNING", count: certWarn.length, to: "/pki" },
    {
      label: "Services with zero endpoints",
      severity: "WARNING",
      count: gapRows.length,
      to: "/network",
    },
    { label: "PVCs not bound", severity: "NOTICE", count: pvcPending.length, to: "/storage" },
  ];
  const attention = attentionAll.filter((item) => item.count > 0);

  const envelope = workloads.data?.envelope;
  const anyError = [workloads, pods, findings, gitops, certificates, gaps, storage].some(
    (query) => query.data?.envelope.errors.length,
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title="Operations Dashboard"
        subtitle={
          <>
            What is broken, what changed, where to look — for{" "}
            <span className="mono">{scope.context || "no context"}</span> /{" "}
            <span className="mono">{scope.namespace || "no namespace"}</span>
          </>
        }
        actions={envelope ? <Freshness envelope={envelope} /> : null}
      />

      {envelope ? <PartialBanner envelope={envelope} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Attention required</CardTitle>
          <Badge tone={attention.length ? "critical" : "ok"}>
            {attention.length ? `${attention.length} categories` : "clear"}
          </Badge>
        </CardHeader>
        <CardBody className="space-y-1.5">
          {attention.length === 0 ? (
            <p className="text-[12.5px] text-text-muted">
              No failing findings detected in the collected data. {workloadRows.length} workloads and{" "}
              {podRows.length} pods checked. This reflects the last successful collection only.
            </p>
          ) : (
            attention.map((item) => (
              <Link
                key={item.label}
                to={item.to}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-2.5 py-1.5 hover:bg-panel-2"
              >
                <span className="flex items-center gap-2">
                  <StatusPill status={item.severity} />
                  <span className="text-[12.5px] text-text">
                    <strong className="mono">{item.count}</strong> {item.label}
                  </span>
                </span>
                <span className="text-[11px] text-text-muted">investigate →</span>
              </Link>
            ))
          )}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        <DomainCard
          title="Workloads"
          to="/workloads"
          primary={`${workloadRows.filter((w) => w.status === "OK").length} / ${workloadRows.length}`}
          caption="Ready / total"
          states={workloadBuckets}
          envelope={envelope}
        />
        <DomainCard
          title="GitOps"
          to="/gitops"
          primary={`${gitopsRows.filter((g) => g.ready === true).length} / ${gitopsRows.length}`}
          caption="Ready / total"
          states={bucket(gitopsRows, (g) => g.status)}
          envelope={gitops.data?.envelope}
        />
        <DomainCard
          title="PKI / TLS"
          to="/pki"
          primary={`${certRows.length}`}
          caption={`${certWarn.length} ≤30 days`}
          states={bucket(certRows, (c) => c.status)}
          envelope={certificates.data?.envelope}
        />
        <DomainCard
          title="Network"
          to="/network"
          primary={`${gapRows.length}`}
          caption="endpoint gaps"
          states={bucket(gapRows, (s) => s.status)}
          envelope={gaps.data?.envelope}
        />
        <DomainCard
          title="Storage"
          to="/storage"
          primary={`${pvcRows.filter((p) => p.severity === "OK").length} / ${pvcRows.length}`}
          caption="Bound / total"
          states={bucket(pvcRows, (p) => p.severity)}
          envelope={storage.data?.envelope}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Latest findings</CardTitle>
          <Link to="/findings" className="text-[11.5px] text-accent">
            Open findings center →
          </Link>
        </CardHeader>
        <CardBody>
          {findingRows.length === 0 ? (
            <p className="text-[12.5px] text-text-muted">
              No failed workloads or failing findings were reported.
            </p>
          ) : (
            <ul className="space-y-1">
              {findingRows.slice(0, 6).map((finding) => (
                <li key={finding.id} className="flex items-start gap-2">
                  <StatusPill status={finding.severity} />
                  <span className="mono text-[11.5px] text-text-muted">{finding.domain}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">
                    {finding.finding}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {anyError ? (
        <p className="text-[11.5px] text-warning">
          Some panels reported errors — open the affected page for the documented reason and the raw
          evidence.
        </p>
      ) : null}
    </div>
  );
}

function DomainCard({
  title,
  to,
  primary,
  caption,
  states,
  envelope,
}: {
  title: string;
  to: string;
  primary: string;
  caption: string;
  states: Record<string, number>;
  envelope: Envelope<unknown> | undefined;
}) {
  const order: Severity[] = ["FAILED", "CRITICAL", "WARNING", "UNKNOWN", "OK"];
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <Link to={to} className="text-[11px] text-accent">
          open →
        </Link>
      </CardHeader>
      <CardBody className="flex-1 space-y-1.5">
        <div className="mono text-[18px] text-text">{primary}</div>
        <div className="text-[11.5px] text-text-muted">{caption}</div>
        <ul className="space-y-0.5">
          {order
            .filter((key) => states[key])
            .map((key) => (
              <li key={key} className="flex items-center justify-between gap-2">
                <StatusPill status={key} />
                <span className="mono text-[11.5px] text-text">{states[key]}</span>
              </li>
            ))}
        </ul>
        {envelope ? (
          <Freshness envelope={envelope} />
        ) : (
          <span className="text-[11px] text-text-faint">not collected</span>
        )}
      </CardBody>
    </Card>
  );
}

