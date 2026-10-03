import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { useEvents } from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import {
  EmptyState,
  ErrorState,
  Freshness,
  LoadingRows,
  PageHeader,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { severityRank } from "@/lib/status";
import { useApp } from "@/state/AppContext";
import type { EventResource } from "@/types";

export function EventsPage() {
  const { scope } = useApp();
  const events = useEvents(scope);
  const [errorsOnly, setErrorsOnly] = useState(false);

  const rows = useMemo(() => {
    const all = [...(events.data?.envelope.data ?? [])].sort(
      (a, b) => severityRank(a.severity) - severityRank(b.severity),
    );
    return errorsOnly
      ? all.filter((e) => e.severity === "CRITICAL" || e.severity === "WARNING")
      : all;
  }, [events.data, errorsOnly]);

  const columns = useMemo<ColumnDef<EventResource, unknown>[]>(
    () => [
      {
        accessorKey: "severity",
        header: "Severity",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
        sortingFn: (a, b) => severityRank(a.original.severity) - severityRank(b.original.severity),
      },
      {
        accessorKey: "time",
        header: "Time",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "reason", header: "Reason" },
      { accessorKey: "object", header: "Object" },
      {
        accessorKey: "count",
        header: "Count",
        cell: (info) => <span className="mono">{String(info.getValue())}</span>,
      },
      { accessorKey: "message", header: "Message" },
    ],
    [],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, number>();
    for (const event of rows) {
      const key = event.reason || "unspecified";
      map.set(key, (map.get(key) ?? 0) + event.count);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [rows]);

  return (
    <div className="space-y-3">
      <PageHeader
        title="Events"
        subtitle={`${rows.length} events · repeated warnings are aggregated with drill-down`}
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setErrorsOnly((v) => !v)}
              className={`rounded-md border px-2 py-1 text-[11.5px] ${
                errorsOnly ? "border-warning/50 text-warning" : "border-border text-text-muted"
              }`}
            >
              Warnings &amp; critical only
            </button>
            {events.data ? <Freshness envelope={events.data.envelope} /> : null}
          </div>
        }
      />

      {events.data ? <PartialBanner envelope={events.data.envelope} /> : null}

      <Tabs defaultValue="table">
        <TabsList>
          <TabsTrigger value="table">TABLE</TabsTrigger>
          <TabsTrigger value="timeline">TIMELINE</TabsTrigger>
        </TabsList>

        <TabsContent value="table">
          <Card>
            <CardBody className="p-0">
              {events.isLoading ? <LoadingRows /> : null}
              {events.data?.envelope.errors.length ? (
                <div className="p-3">
                  <ErrorState envelope={events.data.envelope} onRetry={() => void events.refetch()} />
                </div>
              ) : null}
              {events.data && !events.data.envelope.errors.length ? (
                <DataTable
                  data={rows}
                  columns={columns}
                  exportName="devopssentinel-events"
                  emptyMessage="No events matched the current filter."
                />
              ) : null}
            </CardBody>
          </Card>
        </TabsContent>

        <TabsContent value="timeline">
          <Card>
            <CardBody>
              {rows.length === 0 ? (
                <EmptyState
                  title="No events to display"
                  detail="The engine reported no matching events for this scope."
                />
              ) : (
                <ol className="relative space-y-2 border-l border-border pl-4">
                  {rows.slice(0, 200).map((event, index) => (
                    <li key={index} className="relative">
                      <span
                        className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-border-strong"
                        aria-hidden="true"
                      />
                      <div className="flex items-center gap-2">
                        <span className="mono text-[11px] text-text-muted">{event.time || "—"}</span>
                        <StatusPill status={event.severity} />
                        <span className="text-[12px] text-text">{event.reason || "event"}</span>
                        {event.count > 1 ? <Badge tone="neutral">x{event.count}</Badge> : null}
                      </div>
                      <div className="text-[11.5px] text-text-muted">{event.message}</div>
                    </li>
                  ))}
                </ol>
              )}
            </CardBody>
          </Card>
        </TabsContent>
      </Tabs>

      {grouped.length > 0 ? (
        <Card>
          <CardBody className="space-y-1">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Aggregated reasons
            </h3>
            {grouped.map(([reason, count]) => (
              <div key={reason} className="flex items-center justify-between gap-3">
                <span className="truncate text-[12px] text-text">{reason}</span>
                <span className="mono text-[11.5px] text-text-muted">{count}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}
