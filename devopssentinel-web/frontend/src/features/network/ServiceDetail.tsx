import { X } from "lucide-react";

import { useServiceDns, useServicePortPath } from "@/api/queries";
import {
  ConfidenceTag,
  EmptyState,
  Field,
  LoadingRows,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApp } from "@/state/AppContext";

/**
 * Service workspace: the port path and DNS record for one Service
 * (spec sections 80, 84).
 *
 * Both panels read the engine's own dependency report. The port path is a
 * configuration trace, never a claim that traffic flows at runtime.
 */
export function ServiceDetail({ name, onClose }: { name: string; onClose: () => void }) {
  const { scope } = useApp();
  const portPath = useServicePortPath(scope, name);
  const dns = useServiceDns(scope, name);

  const service = portPath.data?.envelope.data?.service ?? null;
  const edges = portPath.data?.envelope.data?.graph.edges ?? [];
  const record = dns.data?.envelope.data ?? null;

  return (
    <aside
      aria-label={`Service ${name}`}
      className="flex w-full max-w-xl shrink-0 flex-col border-l border-border bg-panel"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <Badge tone="network">Service</Badge>
          <div className="mono mt-1 break-all text-[12.5px] text-text">{name}</div>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto scroll-thin p-3">
        {portPath.isLoading ? <LoadingRows rows={5} /> : null}

        {service ? (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Declaration
            </h3>
            <dl>
              <Field label="Namespace" mono>
                {service.namespace || "—"}
              </Field>
              <Field label="Type" mono>
                {service.type || "—"}
              </Field>
              <Field label="Cluster IP" mono>
                {service.cluster_ip || "—"}
              </Field>
              <Field label="External IP" mono>
                {service.external_ip || "—"}
              </Field>
              <Field label="Ports" mono>
                {service.ports || "—"}
              </Field>
              <Field label="Ready endpoints" mono>
                {service.ready_endpoints} ready · {service.not_ready_endpoints} not ready
              </Field>
              <Field label="Status">
                <StatusPill status={service.status} />
              </Field>
            </dl>
          </section>
        ) : null}

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Port path
          </h3>
          {edges.length === 0 ? (
            <EmptyState
              title="No port path reported"
              detail="The engine reported no ingress, endpoint or workload edges for this Service, so no path can be drawn. Nothing is inferred."
            />
          ) : (
            <ol className="space-y-1">
              {edges.map((edge) => (
                <li key={edge.id} className="border-b border-border/60 pb-1 last:border-0">
                  <div className="mono break-all text-[11.5px] text-text">
                    {edge.source} → {edge.target}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
                    <span>{edge.label}</span>
                    <ConfidenceTag confidence={edge.confidence} />
                  </div>
                  {edge.evidence ? (
                    <div className="mono mt-0.5 break-all text-[10.5px] text-text-faint">
                      {edge.evidence}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
          <p className="mt-1 text-[11px] text-text-faint">
            Configuration trace only. DevOpsSentinel reports the declared mapping; it does not assert
            that traffic reaches the container at runtime.
          </p>
        </section>

        <section className="rounded-md border border-border bg-panel-2 p-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Service DNS
          </h3>
          {dns.isLoading ? <LoadingRows rows={2} /> : null}
          {record ? (
            <>
              <dl>
                <Field label="FQDN" mono>
                  {record.fqdn}
                </Field>
                <Field label="Short name" mono>
                  {record.shortName}
                </Field>
                <Field label="Service address" mono>
                  {record.expectedAddress || "—"}
                </Field>
                <Field label="Ready endpoints" mono>
                  {record.readyEndpoints}
                </Field>
                <Field label="Resolution">
                  <Badge tone={record.resolves === "VERIFIED" ? "ok" : "warning"}>
                    {record.resolves}
                  </Badge>
                </Field>
              </dl>
              <p className="mt-1 text-[11px] text-text-faint">{record.note}</p>
            </>
          ) : null}
        </section>

        <p className="text-[11px] text-text-muted">
          NetworkPolicy isolation for a Pod is reported on the Pod inspector, from the same engine
          dependency report.
        </p>
      </div>
    </aside>
  );
}
