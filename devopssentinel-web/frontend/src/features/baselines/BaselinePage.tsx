import { useState } from "react";

import { useBaselines, useCaptureBaseline, useCompareBaseline } from "@/api/queries";
import { EmptyState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { relative } from "@/lib/format";
import { useApp } from "@/state/AppContext";
import type { ComparisonResult } from "@/types";

const RESULT_TONE: Record<ComparisonResult, "ok" | "warning" | "critical" | "info" | "unknown" | "neutral"> = {
  UNCHANGED: "neutral",
  IMPROVED: "ok",
  DEGRADED: "warning",
  NEW: "info",
  REMOVED: "critical",
  UNKNOWN: "unknown",
};

const STEPS = [
  "CAPTURE PRE",
  "CHANGE OCCURS OUTSIDE DEVOPSSENTINEL",
  "CAPTURE POST",
  "COMPARE",
];

export function BaselinePage() {
  const { scope } = useApp();
  const baselines = useBaselines();
  const capture = useCaptureBaseline();
  const compare = useCompareBaseline();
  const [name, setName] = useState("pre-change");
  const [selected, setSelected] = useState("");

  const rows = compare.data?.data.rows ?? [];

  return (
    <div className="space-y-3">
      <PageHeader
        title="PRE / POST Change Validation"
        subtitle="Capture a baseline, change the cluster outside DevOpsSentinel, capture again, then compare."
        actions={<Badge tone="warning">read-only: DevOpsSentinel never performs the change</Badge>}
      />

      <Card>
        <CardBody className="flex flex-wrap items-center gap-2">
          {STEPS.map((step, index) => (
            <span key={step} className="flex items-center gap-2">
              <span className="rounded border border-border px-2 py-1 text-[11px] uppercase tracking-wide text-text-muted">
                {step}
              </span>
              {index < STEPS.length - 1 ? <span className="text-text-faint">→</span> : null}
            </span>
          ))}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Capture baseline</CardTitle>
            <Badge tone="neutral">
              {scope.context || "—"} / {scope.namespace || "—"}
            </Badge>
          </CardHeader>
          <CardBody className="space-y-2">
            <div className="flex gap-2">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="baseline name"
                aria-label="Baseline name"
              />
              <Button
                onClick={() => capture.mutate({ name, ...scope })}
                disabled={!name.trim() || capture.isPending}
              >
                {capture.isPending ? "Capturing…" : "Capture"}
              </Button>
            </div>
            <p className="text-[11.5px] text-text-muted">
              Baselines are stored locally under{" "}
              <span className="mono">~/.devopssentinel-web</span> and contain only collected resource
              fields — never Secret payloads or credentials.
            </p>
            {capture.isError ? (
              <p className="text-[11.5px] text-critical">
                Capture failed: {(capture.error as Error).message}
              </p>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Stored baselines</CardTitle>
            <Badge tone="neutral">{baselines.data?.data.length ?? 0}</Badge>
          </CardHeader>
          <CardBody className="space-y-1">
            {baselines.isLoading ? <LoadingRows rows={3} /> : null}
            {(baselines.data?.data ?? []).length === 0 && !baselines.isLoading ? (
              <EmptyState
                title="No baselines captured yet"
                detail="Capture a baseline before a change, then capture another afterwards and compare."
              />
            ) : (
              (baselines.data?.data ?? []).map((baseline) => (
                <div
                  key={baseline.name}
                  className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1"
                >
                  <span className="mono truncate text-[12px]">{baseline.name}</span>
                  <span className="text-[11px] text-text-muted">
                    {baseline.namespace || "—"} · {relative(baseline.capturedAt)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelected(baseline.name);
                      compare.mutate({ name: baseline.name });
                    }}
                  >
                    Compare
                  </Button>
                </div>
              ))
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Comparison</CardTitle>
          <div className="flex items-center gap-2">
            {selected ? <Badge tone="neutral">{selected}</Badge> : null}
            {compare.isPending ? <Badge tone="info">comparing…</Badge> : null}
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {compare.isError ? (
            <p className="p-3 text-[12px] text-critical">
              Comparison failed: {(compare.error as Error).message}
            </p>
          ) : null}
          {!compare.data && !compare.isPending && !compare.isError ? (
            <p className="p-3 text-[12px] text-text-muted">
              Select a stored baseline and choose Compare to see what changed.
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className="w-full text-[12px]">
              <thead className="bg-panel-2">
                <tr>
                  {["Resource", "PRE", "POST", "RESULT"].map((heading) => (
                    <th
                      key={heading}
                      scope="col"
                      className="px-3 py-1.5 text-left text-[11px] uppercase tracking-wide text-text-muted"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.resource} className="border-b border-border/50">
                    <td className="mono px-3 py-1">{row.resource}</td>
                    <td className="mono px-3 py-1 text-text-muted">
                      {row.pre.status ?? "—"}
                      {row.pre.restarts !== null && row.pre.restarts !== undefined
                        ? ` · ${row.pre.restarts} restarts`
                        : ""}
                    </td>
                    <td className="mono px-3 py-1 text-text-muted">
                      {row.post.status ?? "—"}
                      {row.post.restarts !== null && row.post.restarts !== undefined
                        ? ` · ${row.post.restarts} restarts`
                        : ""}
                    </td>
                    <td className="px-3 py-1">
                      <Badge tone={RESULT_TONE[row.result] ?? "unknown"}>{row.result}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {compare.data && rows.length === 0 ? (
            <EmptyState
              title="No comparable resources"
              detail="The baseline and the current collection share no resources in this namespace."
            />
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
