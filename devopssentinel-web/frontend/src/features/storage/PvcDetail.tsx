import { X } from "lucide-react";

import { usePvcConsumers, usePvcDetail } from "@/api/queries";
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
 * PVC workspace: the claim's own facts, its binding chain and its consumers
 * (spec sections 85, 86).
 *
 * The binding chain and the consumer list are the engine's dependency edges.
 * An empty consumer list means none were observed, never that none exist.
 */
export function PvcDetail({ name, onClose }: { name: string; onClose: () => void }) {
  const { scope } = useApp();
  const detail = usePvcDetail(scope, name);
  const consumers = usePvcConsumers(scope, name);

  const claim = detail.data?.envelope.data?.claim ?? null;
  const edges = detail.data?.envelope.data?.graph.edges ?? [];
  const direct = consumers.data?.envelope.data?.direct ?? [];

  return (
    <aside
      aria-label={`PersistentVolumeClaim ${name}`}
      className="flex w-full max-w-xl shrink-0 flex-col border-l border-border bg-panel"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <Badge tone="storage">PersistentVolumeClaim</Badge>
          <div className="mono mt-1 break-all text-[12.5px] text-text">{name}</div>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto scroll-thin p-3">
        {detail.isLoading ? <LoadingRows rows={5} /> : null}

        {!detail.isLoading && !claim ? (
          <EmptyState
            title="Not in the storage report"
            detail="This claim was not one of the PersistentVolumeClaims the engine reported for this scope. Relationships, if any, are still shown below."
          />
        ) : null}

        {claim ? (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Claim
            </h3>
            <dl>
              <Field label="Namespace" mono>
                {claim.namespace || "—"}
              </Field>
              <Field label="Status">
                <StatusPill status={claim.status} label={claim.status} />
              </Field>
              <Field label="Capacity" mono>
                {claim.capacity || "—"}
              </Field>
              <Field label="Access modes" mono>
                {claim.access_modes || "—"}
              </Field>
              <Field label="StorageClass" mono>
                {claim.storage_class || "—"}
              </Field>
              <Field label="Volume" mono>
                {claim.volume || "—"}
              </Field>
              <Field label="Severity">
                <Badge tone={claim.severity === "OK" ? "ok" : "warning"}>{claim.severity}</Badge>
              </Field>
            </dl>
          </section>
        ) : null}

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Binding chain
          </h3>
          {edges.length === 0 ? (
            <EmptyState
              title="No binding chain reported"
              detail="The engine reported no Pod → PVC → PV → StorageClass edges for this claim."
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
        </section>

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Consumers ({direct.length})
          </h3>
          {consumers.isLoading ? <LoadingRows rows={2} /> : null}
          {!consumers.isLoading && direct.length === 0 ? (
            <p className="text-[12px] text-text-muted">
              No workload was observed mounting this claim. That is a real signal — an un-consumed
              claim still costs its provisioned volume — but it means none was found in the engine&apos;s
              dependency report, not that none exists.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {direct.map((item) => (
                <li key={item} className="mono text-[12px] text-text">
                  {item}
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="text-[11px] text-text-muted">
          Mount warnings for the whole namespace are listed on the Storage Center page, from the same
          engine report.
        </p>
      </div>
    </aside>
  );
}
