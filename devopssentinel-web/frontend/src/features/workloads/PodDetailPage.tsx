import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { useGraph, usePod, usePodEvents, usePodLogs } from "@/api/queries";
import {
  ErrorState,
  Field,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  RawView,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { reportText } from "@/lib/format";
import { useApp } from "@/state/AppContext";

export function PodDetailPage() {
  const { name = "" } = useParams();
  const { scope, setSelection } = useApp();
  const [filter, setFilter] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);

  const pod = usePod(scope, name);
  const events = usePodEvents(scope, name);
  const logs = usePodLogs(scope, name);
  const graph = useGraph(scope, "Pod", name);

  const lines = logs.data?.envelope.data.lines ?? [];
  const visibleLines = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return lines.filter((line) => {
      if (errorsOnly && line.level !== "ERROR") return false;
      if (needle && !line.text.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [lines, filter, errorsOnly]);

  return (
    <div className="space-y-3">
      <PageHeader
        title={`Pod ${name}`}
        subtitle={<span className="mono">namespace {scope.namespace || "—"}</span>}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setSelection({ kind: "Pod", name })}>
              Inspect relations
            </Button>
            {pod.data ? <Freshness envelope={pod.data.envelope} /> : null}
          </div>
        }
      />

      {pod.data ? <PartialBanner envelope={pod.data.envelope} /> : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Report</CardTitle>
            <Badge tone="neutral">engine triage</Badge>
          </CardHeader>
          <CardBody>
            {pod.isLoading ? <LoadingRows /> : null}
            {pod.data?.envelope.errors.length ? (
              <ErrorState envelope={pod.data.envelope} onRetry={() => void pod.refetch()} />
            ) : null}
            {pod.data ? (
              <pre className="mono max-h-[420px] overflow-auto whitespace-pre-wrap rounded bg-bg-elevated p-2 text-[11.5px] text-text-muted">
                {reportText(pod.data.envelope.data)}
              </pre>
            ) : null}
          </CardBody>
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle>Relations</CardTitle>
            </CardHeader>
            <CardBody className="space-y-1">
              {graph.data?.envelope.data.nodes.length ? (
                graph.data.envelope.data.nodes.map((node) => (
                  <div key={node.id} className="flex items-center justify-between gap-2">
                    <span className="mono truncate text-[11.5px]">{node.id}</span>
                    <StatusPill status={node.state} />
                  </div>
                ))
              ) : (
                <p className="text-[11.5px] text-text-muted">No dependency rows reported.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Events</CardTitle>
            </CardHeader>
            <CardBody>
              {(events.data?.envelope.data ?? []).slice(0, 8).map((event, index) => (
                <dl key={index}>
                  <Field label="Time" mono>
                    {event.time || "—"}
                  </Field>
                  <Field label="Reason">{event.reason || "—"}</Field>
                  <Field label="Count" mono>
                    {event.count}
                  </Field>
                </dl>
              ))}
              {(events.data?.envelope.data ?? []).length === 0 ? (
                <p className="text-[11.5px] text-text-muted">No events captured in this report.</p>
              ) : null}
            </CardBody>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Logs</CardTitle>
          <div className="flex items-center gap-2">
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Search logs…"
              className="h-7 w-52"
              aria-label="Search logs"
            />
            <Button
              variant={errorsOnly ? "primary" : "outline"}
              size="sm"
              onClick={() => setErrorsOnly((v) => !v)}
            >
              ERROR only
            </Button>
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {logs.data?.envelope.partial ? (
            <div className="border-b border-border px-3 py-1.5 text-[11.5px] text-warning">
              PARTIAL — {logs.data.envelope.warnings[0]}
            </div>
          ) : null}
          <pre className="mono max-h-[420px] overflow-auto whitespace-pre-wrap bg-bg-elevated p-2 text-[11.5px]">
            {visibleLines.length === 0
              ? "No log lines matched the current filter."
              : visibleLines
                  .map(
                    (line) =>
                      `${String(line.n).padStart(6, " ")}  ${line.level.padEnd(5)}  ${line.text}`,
                  )
                  .join("\n")}
          </pre>
        </CardBody>
      </Card>

      {(logs.data?.envelope.data.patterns ?? []).length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Repeated patterns</CardTitle>
          </CardHeader>
          <CardBody className="space-y-0.5">
            {logs.data!.envelope.data.patterns.map((pattern) => (
              <div key={pattern.pattern} className="flex items-center justify-between gap-3">
                <span className="mono truncate text-[11.5px] text-text-muted">{pattern.pattern}</span>
                <span className="mono text-[11.5px] text-text">{pattern.count}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <RawView raw={pod.data?.raw} />
    </div>
  );
}

