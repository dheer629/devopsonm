import { Download, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useContainers, useLogs, usePods } from "@/api/queries";
import { ErrorState, LoadingRows, PageHeader, RawView } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/primitives";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useApp } from "@/state/AppContext";
import type { LogLine } from "@/types";

/** Bounded time windows the viewer offers (mirrors the API's `SINCE_OPTIONS`). */
const SINCE_OPTIONS = [
  { value: "none", label: "No time limit" },
  { value: "5m", label: "Last 5 minutes" },
  { value: "15m", label: "Last 15 minutes" },
  { value: "30m", label: "Last 30 minutes" },
  { value: "1h", label: "Last 1 hour" },
  { value: "6h", label: "Last 6 hours" },
  { value: "24h", label: "Last 24 hours" },
];

const TAIL_OPTIONS = ["100", "500", "1000", "5000", "20000"];

const LEVELS = ["ALL", "ERROR", "WARN", "INFO", "DEBUG"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_CLASS: Record<string, string> = {
  ERROR: "text-critical",
  WARN: "text-warning",
  INFO: "text-text",
  DEBUG: "text-text-faint",
};

const FOLLOW_MS = 5000;

export function LogsPage() {
  const { scope } = useApp();
  const pods = usePods(scope, Boolean(scope.namespace));

  const [pod, setPod] = useState("");
  const [container, setContainer] = useState("");
  const [tail, setTail] = useState("500");
  const [since, setSince] = useState("none");
  const [previous, setPrevious] = useState(false);
  const [timestamps, setTimestamps] = useState(true);
  const [follow, setFollow] = useState(false);
  const [wrap, setWrap] = useState(false);
  const [level, setLevel] = useState<Level>("ALL");
  const [filter, setFilter] = useState("");

  const podNames = useMemo(
    () => [...(pods.data?.envelope.data ?? [])].map((item) => item.name).sort(),
    [pods.data],
  );

  // Auto-select the first pod once the inventory arrives.
  useEffect(() => {
    if (!pod && podNames.length) setPod(podNames[0]);
  }, [pod, podNames]);

  const containers = useContainers(scope, pod, Boolean(pod) && Boolean(scope.namespace));
  const containerNames = useMemo(
    () => containers.data?.data.containers ?? [],
    [containers.data],
  );

  // Keep the container picker valid when the pod changes.
  useEffect(() => {
    if (containerNames.length && !containerNames.includes(container)) {
      setContainer(containerNames[0]);
    } else if (!containerNames.length && container) {
      setContainer("");
    }
  }, [containerNames, container]);

  const logs = useLogs(
    scope,
    {
      pod,
      container,
      tail: Number(tail),
      since: since === "none" ? "" : since,
      previous,
      timestamps,
    },
    Boolean(pod) && Boolean(scope.namespace),
    follow ? FOLLOW_MS : false,
  );

  const lines = logs.data?.envelope.data.lines ?? [];
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return lines.filter((line) => {
      if (level !== "ALL" && line.level !== level) return false;
      if (needle && !line.text.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [lines, level, filter]);

  const patterns = logs.data?.envelope.data.patterns ?? [];
  const canRead = Boolean(scope.namespace);

  function download() {
    const text = visible
      .map((line) => `${line.ts ? `${line.ts} ` : ""}${line.level.padEnd(5)} ${line.text}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `logs-${pod}${container ? `-${container}` : ""}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3">
      <PageHeader
        title="Log Viewer"
        subtitle={
          <>
            Read-only <span className="mono">kubectl logs</span> for one pod container — pod,
            container, stream, tail and time window are all selectable.
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="neutral">namespace {scope.namespace || "—"}</Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void logs.refetch()}
              disabled={!pod}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh now
            </Button>
          </div>
        }
      />

      {!canRead ? (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning">
          A namespace is required — select one in the left navigation to read pod logs.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Options</CardTitle>
          {logs.data ? (
            <span className="mono text-[11px] text-text-muted">
              {logs.data.envelope.data.lines.length} lines · tail {logs.data.envelope.data.tail}
              {logs.data.envelope.data.since ? ` · since ${logs.data.envelope.data.since}` : ""}
            </span>
          ) : null}
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Pod">
            <Select value={pod || undefined} onValueChange={setPod}>
              <SelectTrigger aria-label="Pod">
                <SelectValue placeholder={podNames.length ? "Select pod" : "No pods"} />
              </SelectTrigger>
              <SelectContent>
                {podNames.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Container">
            <Select value={container || undefined} onValueChange={setContainer}>
              <SelectTrigger aria-label="Container">
                <SelectValue placeholder={containerNames.length ? "Select container" : "Auto"} />
              </SelectTrigger>
              <SelectContent>
                {containerNames.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Time window">
            <Select value={since} onValueChange={setSince}>
              <SelectTrigger aria-label="Time window">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SINCE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Tail lines">
            <Select value={tail} onValueChange={setTail}>
              <SelectTrigger aria-label="Tail lines">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TAIL_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Stream">
            <div className="pt-1 text-[12px] text-text">
              <label className="inline-flex items-center gap-1.5">
                <Switch
                  checked={previous}
                  onCheckedChange={setPrevious}
                  aria-label="Previous instance"
                />
                Previous instance
              </label>
            </div>
          </Field>

          <Field label="Display">
            <div className="flex flex-wrap items-center gap-3 pt-1 text-[12px] text-text">
              <label className="inline-flex items-center gap-1.5">
                <Switch checked={timestamps} onCheckedChange={setTimestamps} aria-label="Timestamps" />
                Timestamps
              </label>
              <label className="inline-flex items-center gap-1.5">
                <Switch checked={wrap} onCheckedChange={setWrap} aria-label="Wrap lines" />
                Wrap
              </label>
              <label className="inline-flex items-center gap-1.5">
                <Switch checked={follow} onCheckedChange={setFollow} aria-label="Follow logs" />
                Follow
              </label>
            </div>
          </Field>

          <Field label="Filter">
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Search log text…"
              aria-label="Search logs"
            />
          </Field>

          <Field label="Level">
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              {LEVELS.map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={level === item}
                  onClick={() => setLevel(item)}
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[11px]",
                    level === item
                      ? "border-accent/50 text-accent"
                      : "border-border text-text-muted hover:text-text",
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          </Field>
        </CardBody>
      </Card>

      {logs.isLoading ? <LoadingRows /> : null}
      {logs.data?.envelope.errors.length ? (
        <ErrorState envelope={logs.data.envelope} onRetry={() => void logs.refetch()} />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{pod ? `${pod}${container ? ` · ${container}` : ""}` : "Logs"}</CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-text-muted">
              {visible.length} of {lines.length} lines
            </span>
            <Button variant="outline" size="sm" onClick={download} disabled={!visible.length}>
              <Download className="h-3.5 w-3.5" /> Download
            </Button>
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {logs.data && !logs.data.envelope.errors.length ? (
            <LogLines lines={visible} wrap={wrap} showTs={timestamps} />
          ) : null}
        </CardBody>
      </Card>

      {patterns.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Repeated patterns</CardTitle>
          </CardHeader>
          <CardBody className="space-y-0.5">
            {patterns.map((pattern) => (
              <div key={pattern.pattern} className="flex items-center justify-between gap-3">
                <span className="mono truncate text-[11.5px] text-text-muted">{pattern.pattern}</span>
                <span className="mono text-[11.5px] text-text">{pattern.count}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <p className="text-[11px] text-text-muted">
        Logs are read with a single bounded <span className="mono">kubectl logs</span> call
        (tail + optional time window). Follow re-reads every {FOLLOW_MS / 1000}s; it is a poll, not a
        live stream. Output is redacted before it leaves the backend and never written to disk.
      </p>

      <RawView raw={logs.data?.raw} />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
        {label}
      </div>
      {children}
    </div>
  );
}

function LogLines({
  lines,
  wrap,
  showTs,
}: {
  lines: LogLine[];
  wrap: boolean;
  showTs: boolean;
}) {
  if (lines.length === 0) {
    return (
      <p className="px-3 py-8 text-center text-[12px] text-text-muted">
        No log lines matched the current filter. The container may not have produced output for the
        selected window.
      </p>
    );
  }
  return (
    <div className="mono max-h-[560px] overflow-auto bg-bg-elevated p-2 text-[11.5px]">
      {lines.map((line) => (
        <div
          key={line.n}
          className={cn("flex gap-2", wrap ? "whitespace-pre-wrap" : "whitespace-pre")}
        >
          <span className="w-12 shrink-0 select-none text-right text-text-faint">{line.n}</span>
          {showTs ? <span className="shrink-0 text-text-faint">{line.ts || "—"}</span> : null}
          <span className={cn("w-12 shrink-0", LEVEL_CLASS[line.level] ?? "text-text")}>
            {line.level}
          </span>
          <span
            className={cn(
              "min-w-0 flex-1",
              wrap && "break-all",
              LEVEL_CLASS[line.level] ?? "text-text",
            )}
          >
            {line.text}
          </span>
        </div>
      ))}
    </div>
  );
}
