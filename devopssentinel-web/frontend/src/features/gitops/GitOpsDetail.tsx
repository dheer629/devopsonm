import { X } from "lucide-react";

import { useGitOpsDetail, useGitOpsTimeline } from "@/api/queries";
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
 * GitOps object workspace: the chain it manages and its revision state
 * (spec sections 77, 78).
 *
 * DevOpsSentinel is a supervision tool, so this view never offers Reconcile,
 * Suspend, Resume, Upgrade or Rollback. A revision difference is reported as
 * possible reconciliation lag, not as proven drift.
 */
export function GitOpsDetail({
  kind,
  name,
  onClose,
}: {
  kind: string;
  name: string;
  onClose: () => void;
}) {
  const { scope } = useApp();
  const detail = useGitOpsDetail(scope, kind, name);
  const timeline = useGitOpsTimeline(scope, kind, name);

  const object = detail.data?.envelope.data?.object ?? null;
  const edges = detail.data?.envelope.data?.graph.edges ?? [];
  const entries = timeline.data?.envelope.data?.entries ?? [];
  const lagging = timeline.data?.envelope.data?.lagging ?? false;

  return (
    <aside
      aria-label={`${kind} ${name}`}
      className="flex w-full max-w-xl shrink-0 flex-col border-l border-border bg-panel"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <Badge tone="gitops">{kind}</Badge>
          <div className="mono mt-1 break-all text-[12.5px] text-text">{name}</div>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto scroll-thin p-3">
        {detail.isLoading ? <LoadingRows rows={5} /> : null}

        {object ? (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Object
            </h3>
            <dl>
              <Field label="Namespace" mono>
                {object.namespace || "—"}
              </Field>
              <Field label="Ready">
                {object.ready === null ? (
                  <StatusPill status="UNKNOWN" />
                ) : (
                  <StatusPill
                    status={object.ready ? "OK" : "FAILED"}
                    label={object.ready ? "Ready" : "Failed"}
                  />
                )}
              </Field>
              <Field label="Suspended">
                <Badge tone={object.suspended ? "warning" : "neutral"}>
                  {object.suspended ? "SUSPENDED" : "active"}
                </Badge>
              </Field>
              <Field label="Desired revision" mono>
                {object.revision || "—"}
              </Field>
              <Field label="Applied revision" mono>
                {object.applied_revision || "—"}
              </Field>
              <Field label="Status">
                <StatusPill status={object.status} />
              </Field>
              <Field label="Message" mono>
                <span title={object.message}>{object.message || "—"}</span>
              </Field>
            </dl>
          </section>
        ) : null}

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Managed chain
          </h3>
          {edges.length === 0 ? (
            <EmptyState
              title="No managed objects reported"
              detail="The engine reported no chain from this object to the workloads it manages, so none is drawn. Nothing is inferred."
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
          <h3 className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Revision state
            {lagging ? <Badge tone="warning">LAGGING</Badge> : null}
          </h3>
          {timeline.isLoading ? <LoadingRows rows={3} /> : null}
          {!timeline.isLoading && entries.length === 0 ? (
            <p className="text-[12px] text-text-muted">
              The engine reported no revision information for this object.
            </p>
          ) : (
            <ol className="space-y-1">
              {entries.map((entry) => (
                <li
                  key={`${entry.event}-${entry.revision}`}
                  className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-1 last:border-0"
                >
                  <StatusPill status={entry.status} />
                  <span className="text-[12px] text-text">{entry.event}</span>
                  <span className="mono text-[11px] text-text-muted">{entry.revision || "—"}</span>
                  <span className="ml-auto text-[11px] text-text-faint">{entry.detail}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-1 text-[11px] text-text-faint">
            {timeline.data?.envelope.data?.note ??
              "The engine reports the current and applied revision, not a revision history."}
          </p>
        </section>

        <section className="rounded-md border border-border bg-panel-2 p-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Supervision only
          </h3>
          <p className="mt-1 text-[11.5px] text-text-muted">
            DevOpsSentinel never offers Reconcile, Suspend, Resume, Upgrade or Rollback. A difference
            between the desired and applied revision may be reconciliation lag rather than manifest
            drift, and is reported as such.
          </p>
        </section>
      </div>
    </aside>
  );
}
