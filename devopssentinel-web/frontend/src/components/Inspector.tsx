import { ExternalLink, Pin, X } from "lucide-react";
import { Link } from "react-router-dom";

import { useGraph, useImpact, useAddPin } from "@/api/queries";
import { ConfidenceTag, EmptyState, ErrorState, Field, LoadingRows, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApp } from "@/state/AppContext";

/** Right-hand context inspector: selected resource, relations, actions. */
export function Inspector() {
  const { selection, setSelection, scope, inspectorOpen, setInspectorOpen } = useApp();
  const graph = useGraph(scope, selection?.kind ?? "", selection?.name ?? "", Boolean(selection));
  const impact = useImpact(scope, selection?.kind ?? "", selection?.name ?? "", Boolean(selection));
  const addPin = useAddPin();

  if (!inspectorOpen) return null;

  return (
    <aside
      aria-label="Context inspector"
      className="flex w-[340px] shrink-0 flex-col border-l border-border bg-panel"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <h2 className="text-[12px] font-semibold uppercase tracking-wide text-text-muted">
          Context Inspector
        </h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          aria-label="Close inspector"
          onClick={() => setInspectorOpen(false)}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {!selection ? (
        <EmptyState
          title="No resource selected"
          detail="Select a row in any table or a node in the topology graph to inspect its relations, evidence and actions."
        />
      ) : (
        <div className="flex-1 space-y-3 overflow-y-auto scroll-thin p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <Badge tone="kubernetes">{selection.kind}</Badge>
              <div className="mono mt-1 break-all text-[12.5px] text-text">{selection.name}</div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              aria-label="Pin resource"
              onClick={() =>
                addPin.mutate({
                  id: `${selection.kind}/${selection.name}`,
                  kind: selection.kind,
                  name: selection.name,
                  context: scope.context ?? "",
                  namespace: scope.namespace ?? "",
                  health: "UNKNOWN",
                })
              }
            >
              <Pin className="h-3.5 w-3.5" />
            </Button>
          </div>

          <dl className="rounded-md border border-border bg-panel-2 px-2 py-1">
            <Field label="Context" mono>
              {scope.context || "—"}
            </Field>
            <Field label="Namespace" mono>
              {scope.namespace || "—"}
            </Field>
          </dl>

          <section>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Dependency graph
            </h3>
            {graph.isLoading ? <LoadingRows rows={4} /> : null}
            {graph.data?.envelope.errors.length ? (
              <ErrorState envelope={graph.data.envelope} />
            ) : null}
            {graph.data ? (
              <ul className="space-y-1">
                {graph.data.envelope.data.nodes.map((node) => (
                  <li key={node.id} className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      className="mono truncate text-left text-[11.5px] text-text hover:text-accent"
                      onClick={() => setSelection({ kind: node.kind, name: node.name })}
                    >
                      {node.id}
                    </button>
                    <StatusPill status={node.state} />
                  </li>
                ))}
                {graph.data.envelope.data.nodes.length === 0 ? (
                  <li className="text-[11.5px] text-text-muted">No relations reported.</li>
                ) : null}
              </ul>
            ) : null}
          </section>

          <section>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              What references this?
            </h3>
            {impact.data ? (
              <>
                <div className="mb-1">
                  <ConfidenceTag confidence={impact.data.envelope.data.confidence ?? "HIGH CONFIDENCE"} />
                </div>
                <ul className="space-y-1">
                  {impact.data.envelope.data.direct.map((ref) => (
                    <li key={ref} className="mono truncate text-[11.5px] text-text">
                      {ref}
                    </li>
                  ))}
                  {impact.data.envelope.data.direct.length === 0 ? (
                    <li className="text-[11.5px] text-text-muted">No direct references found.</li>
                  ) : null}
                </ul>
              </>
            ) : (
              <p className="text-[11.5px] text-text-muted">
                Reverse dependencies are derived from the engine's dependency report.
              </p>
            )}
          </section>

          <div className="flex flex-wrap gap-1">
            <Button variant="outline" size="sm" asChild>
              <Link to={`/topology?kind=${selection.kind}&name=${selection.name}`}>
                <ExternalLink className="h-3.5 w-3.5" /> Open topology
              </Link>
            </Button>
            {selection.kind.toLowerCase() === "pod" ? (
              <Button variant="outline" size="sm" asChild>
                <Link to={`/workloads/pods/${selection.name}`}>Open pod</Link>
              </Button>
            ) : null}
          </div>
        </div>
      )}
    </aside>
  );
}
