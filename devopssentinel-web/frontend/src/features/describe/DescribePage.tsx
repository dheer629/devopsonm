import type { ColumnDef } from "@tanstack/react-table";
import { Copy, Download, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  useCertificates,
  useDescribe,
  useGitOps,
  usePods,
  useServices,
  useStorage,
  useWorkloads,
} from "@/api/queries";
import { DataTable } from "@/components/DataTable";
import { ErrorState, LoadingRows, PageHeader, RawView, StatusPill } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApp } from "@/state/AppContext";
import type { ResourceEvent } from "@/types";

/**
 * Kind catalogue for the description viewer.
 *
 * `from` names the inventory that already lists objects of this kind, so the
 * name picker can be populated instead of typed. `Secret` is deliberately
 * absent: the backend and the kubectl allowlist both refuse it.
 */
const KINDS = [
  { label: "Pod", kind: "Pod", from: "pods" },
  { label: "Deployment", kind: "Deployment", from: "workloads" },
  { label: "StatefulSet", kind: "StatefulSet", from: "workloads" },
  { label: "DaemonSet", kind: "DaemonSet", from: "workloads" },
  { label: "Job", kind: "Job", from: "workloads" },
  { label: "CronJob", kind: "CronJob", from: "workloads" },
  { label: "Service", kind: "Service", from: "services" },
  { label: "PersistentVolumeClaim", kind: "PersistentVolumeClaim", from: "storage" },
  { label: "Certificate", kind: "Certificate", from: "certificates" },
  { label: "HelmRelease", kind: "HelmRelease", from: "gitops" },
  { label: "Kustomization", kind: "Kustomization", from: "gitops" },
  { label: "GitRepository", kind: "GitRepository", from: "gitops" },
  { label: "ConfigMap", kind: "ConfigMap", from: "none" },
  { label: "ServiceAccount", kind: "ServiceAccount", from: "none" },
  { label: "Ingress", kind: "Ingress", from: "none" },
  { label: "NetworkPolicy", kind: "NetworkPolicy", from: "none" },
  { label: "HorizontalPodAutoscaler", kind: "HorizontalPodAutoscaler", from: "none" },
] as const;

const FORMATS = ["describe", "yaml", "json", "events"] as const;
type Format = (typeof FORMATS)[number];

const FORMAT_LABEL: Record<Format, string> = {
  describe: "Describe",
  yaml: "YAML",
  json: "JSON",
  events: "Events",
};

export function DescribePage() {
  const { scope } = useApp();
  const [kind, setKind] = useState("Pod");
  const [name, setName] = useState("");
  const [format, setFormat] = useState<Format>("describe");
  const [manualName, setManualName] = useState("");

  const from = KINDS.find((option) => option.kind === kind)?.from ?? "none";
  const scoped = Boolean(scope.namespace);

  const pods = usePods(scope, scoped && from === "pods");
  const workloads = useWorkloads(scope, scoped && from === "workloads");
  const services = useServices(scope, scoped && from === "services");
  const storage = useStorage(scope, scoped && from === "storage");
  const certificates = useCertificates(scope, scoped && from === "certificates");
  const gitops = useGitOps(scope, scoped && from === "gitops");

  const names = useMemo(() => {
    const set = new Set<string>();
    if (from === "pods") {
      for (const pod of pods.data?.envelope.data ?? []) set.add(pod.name);
    } else if (from === "workloads") {
      for (const item of workloads.data?.envelope.data ?? []) {
        if (item.kind === kind) set.add(item.name);
      }
    } else if (from === "services") {
      for (const item of services.data?.envelope.data ?? []) set.add(item.name);
    } else if (from === "storage") {
      for (const item of storage.data?.envelope.data ?? []) set.add(item.name);
    } else if (from === "certificates") {
      for (const item of certificates.data?.envelope.data ?? []) set.add(item.name);
    } else if (from === "gitops") {
      for (const item of gitops.data?.envelope.data ?? []) {
        if (item.kind === kind) set.add(item.name);
      }
    }
    return [...set].sort();
  }, [
    from,
    kind,
    pods.data,
    workloads.data,
    services.data,
    storage.data,
    certificates.data,
    gitops.data,
  ]);

  // Keep the selection valid: pick the first discoverable name, else free text.
  useEffect(() => {
    if (names.length && !names.includes(name)) setName(names[0]);
    if (!names.length && from !== "none") setName("");
  }, [names, name, from]);

  const effectiveName = from === "none" ? manualName : name;

  const described = useDescribe(
    scope,
    { kind, name: effectiveName, format },
    scoped && Boolean(effectiveName),
  );

  const data = described.data?.envelope.data;
  const content = data?.content ?? "";
  const events = data?.events ?? [];

  function copy() {
    if (!content) return;
    void navigator.clipboard?.writeText(content);
  }

  function download() {
    const body = format === "events" ? JSON.stringify(events, null, 2) : content;
    const blob = new Blob([body], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${kind}-${effectiveName || "resource"}.${
      format === "describe" ? "txt" : format
    }`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const eventColumns = useMemo<ColumnDef<ResourceEvent, unknown>[]>(
    () => [
      {
        accessorKey: "time",
        header: "Time",
        cell: (info) => <span className="mono">{String(info.getValue() || "—")}</span>,
      },
      {
        accessorKey: "type",
        header: "Type",
        cell: (info) => <StatusPill status={String(info.getValue())} />,
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

  return (
    <div className="space-y-3">
      <PageHeader
        title="Resource Description"
        subtitle={
          <>
            Read-only <span className="mono">kubectl describe</span> /{" "}
            <span className="mono">get -o yaml|json</span> / events for one object. Secret is never
            readable here.
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="neutral">namespace {scope.namespace || "—"}</Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void described.refetch()}
              disabled={!effectiveName}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh now
            </Button>
          </div>
        }
      />

      {!scoped ? (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning">
          A namespace is required — select one in the left navigation.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Target</CardTitle>
          {described.data ? (
            <span className="mono text-[11px] text-text-muted">
              {kind}/{effectiveName} · {FORMAT_LABEL[format].toLowerCase()} ·{" "}
              {described.data.envelope.durationMs}ms
            </span>
          ) : null}
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <div className="pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
              Kind
            </div>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger aria-label="Kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((option) => (
                  <SelectItem key={option.kind} value={option.kind}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2">
            <div className="pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
              Name
            </div>
            {from === "none" ? (
              <Input
                value={manualName}
                onChange={(event) => setManualName(event.target.value)}
                placeholder={`${kind} name`}
                aria-label="Resource name"
              />
            ) : (
              <Select value={name || undefined} onValueChange={setName}>
                <SelectTrigger aria-label="Resource name">
                  <SelectValue placeholder={names.length ? "Select name" : "None discovered"} />
                </SelectTrigger>
                <SelectContent>
                  {names.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div>
            <div className="pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
              Output
            </div>
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              {FORMATS.map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={format === item}
                  onClick={() => setFormat(item)}
                  className={`rounded-full border px-2.5 py-0.5 text-[11.5px] ${
                    format === item
                      ? "border-accent/50 text-accent"
                      : "border-border text-text-muted hover:text-text"
                  }`}
                >
                  {FORMAT_LABEL[item]}
                </button>
              ))}
            </div>
          </div>
        </CardBody>
      </Card>

      {described.isLoading ? <LoadingRows /> : null}
      {described.data?.envelope.errors.length ? (
        <ErrorState envelope={described.data.envelope} onRetry={() => void described.refetch()} />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{FORMAT_LABEL[format]}</CardTitle>
          <div className="flex items-center gap-2">
            {format === "events" ? (
              <span className="text-[11px] text-text-muted">{events.length} events</span>
            ) : (
              <span className="text-[11px] text-text-muted">
                {content ? `${content.split("\n").length} lines` : "no output"}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={copy} disabled={!content}>
              <Copy className="h-3.5 w-3.5" /> Copy
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={download}
              disabled={!content && events.length === 0}
            >
              <Download className="h-3.5 w-3.5" /> Download
            </Button>
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {format === "events" ? (
            <DataTable
              data={events}
              columns={eventColumns}
              exportName={`${kind}-${effectiveName}-events`}
              emptyMessage="No events involve this object in the selected namespace."
            />
          ) : described.data && !described.data.envelope.errors.length ? (
            <pre className="mono max-h-[560px] overflow-auto whitespace-pre-wrap bg-bg-elevated p-3 text-[11.5px] text-text">
              {content || "No output was returned for this object."}
            </pre>
          ) : null}
        </CardBody>
      </Card>

      <p className="text-[11px] text-text-muted">
        Secret is excluded by the backend and by the kubectl allowlist, so a Secret payload is never
        requested. Output is redacted before it leaves the backend and never written to disk.
      </p>

      <RawView raw={described.data?.raw} />
    </div>
  );
}
