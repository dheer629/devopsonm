import { AlertTriangle, Inbox, RefreshCw, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/primitives";
import { freshness } from "@/lib/format";
import { CONFIDENCE_STYLE, SEVERITY, severityOf, type Confidence } from "@/lib/status";
import { cn } from "@/lib/utils";
import type { Envelope, RawEvidence, Source } from "@/types";

/** Status is always icon + text + colour, never colour alone (spec 12). */
export function StatusPill({
  status,
  label,
  className,
}: {
  status: string;
  label?: string;
  className?: string;
}) {
  const sev = severityOf(status);
  const style = SEVERITY[sev];
  return (
    <span className={cn("inline-flex items-center gap-1 text-[12px]", style.className, className)}>
      <span aria-hidden="true">{style.glyph}</span>
      <span>{label ?? style.label}</span>
    </span>
  );
}

export function ConfidenceTag({ confidence }: { confidence: string }) {
  const key = (confidence || "UNKNOWN").toUpperCase() as Confidence;
  const cls = CONFIDENCE_STYLE[key] ?? CONFIDENCE_STYLE.UNKNOWN;
  return (
    <span className={cn("text-[11px] font-medium", cls)} title={`Relationship confidence: ${key}`}>
      {key}
    </span>
  );
}

const SOURCE_TONE: Record<Source, string> = {
  LIVE: "text-success",
  CACHE: "text-info",
  LOCAL: "text-text-muted",
  PARTIAL: "text-warning",
  UNAVAILABLE: "text-critical",
};

export function Freshness({ envelope }: { envelope: Envelope<unknown> }) {
  return (
    <span
      className={cn("mono text-[11px]", SOURCE_TONE[envelope.source] ?? "text-text-muted")}
      title={`source=${envelope.source} duration=${envelope.durationMs}ms cacheAge=${envelope.cacheAgeMs}ms`}
    >
      {freshness(envelope.source, envelope.durationMs, envelope.cacheAgeMs, envelope.timestamp)}
    </span>
  );
}

export function PartialBanner({ envelope }: { envelope: Envelope<unknown> }) {
  if (!envelope.partial && envelope.source !== "PARTIAL") return null;
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <div>
        <strong className="font-semibold">PARTIAL DATA</strong>
        <div className="text-text-muted">
          {envelope.warnings.length > 0
            ? envelope.warnings.join(" ")
            : "Some collectors did not complete; this inventory is incomplete."}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  kind = "EMPTY",
}: {
  title: string;
  detail: string;
  kind?: "EMPTY" | "UNAVAILABLE" | "FAILED" | "PARTIAL";
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Inbox className="h-5 w-5 text-text-faint" aria-hidden="true" />
      <div className="text-[13px] font-medium text-text">
        <Badge tone="neutral" className="mr-2 align-middle">
          {kind}
        </Badge>
        {title}
      </div>
      <p className="max-w-md text-[12px] text-text-muted">{detail}</p>
    </div>
  );
}

export function ErrorState({
  envelope,
  onRetry,
}: {
  envelope: Envelope<unknown>;
  onRetry?: () => void;
}) {
  const reason = envelope.errors[0] ?? "UNKNOWN";
  return (
    <div
      role="alert"
      className="rounded-md border border-critical/40 bg-critical/10 px-3 py-3 text-[12.5px]"
    >
      <div className="flex items-center gap-2 text-critical">
        <ShieldAlert className="h-4 w-4" aria-hidden="true" />
        <strong className="font-semibold">Unable to retrieve data</strong>
      </div>
      <dl className="mt-2 space-y-1 text-text-muted">
        <div>
          <dt className="inline font-medium text-text">Reason </dt>
          <dd className="mono inline">{reason}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-text">Impact </dt>
          <dd className="inline">This view may be incomplete.</dd>
        </div>
        <div>
          <dt className="inline font-medium text-text">Next safe action </dt>
          <dd className="inline">Continue with other domains; the engine remains read-only.</dd>
        </div>
      </dl>
      <details className="mt-2">
        <summary className="cursor-pointer text-text-muted">Technical details</summary>
        <pre className="mono mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-bg-elevated p-2 text-[11px] text-text-muted">
          {JSON.stringify(
            { errors: envelope.errors, warnings: envelope.warnings, source: envelope.source },
            null,
            2,
          )}
        </pre>
      </details>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </Button>
      ) : null}
    </div>
  );
}

export function LoadingRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-1.5 p-3">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-6 w-full" />
      ))}
    </div>
  );
}

export function RawView({ raw }: { raw: RawEvidence | undefined }) {
  if (!raw) return null;
  return (
    <details className="rounded-md border border-border bg-panel-2">
      <summary className="cursor-pointer px-3 py-2 text-[12px] font-medium text-text-muted">
        Raw expert view
      </summary>
      <div className="space-y-2 border-t border-border p-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-text-faint">Read-only command</div>
          <code className="mono block overflow-x-auto whitespace-pre rounded bg-bg-elevated p-2 text-[11.5px]">
            {raw.readOnlyCommand}
          </code>
        </div>
        <div className="text-[11px] text-text-muted">
          exit status <span className="mono">{raw.exitStatus}</span> • duration{" "}
          <span className="mono">{raw.durationMs}ms</span>
        </div>
        <details>
          <summary className="cursor-pointer text-[11.5px] text-text-muted">Raw JSON</summary>
          <pre className="mono mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-bg-elevated p-2 text-[11px]">
            {raw.stdout}
          </pre>
        </details>
      </div>
    </details>
  );
}

export function Field({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1 last:border-0">
      <dt className="shrink-0 text-[11.5px] text-text-muted">{label}</dt>
      <dd className={cn("truncate text-right text-[12px] text-text", mono && "mono")}>{children}</dd>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2 pb-3">
      <div>
        <h1 className="text-[15px] font-semibold text-text">{title}</h1>
        {subtitle ? <div className="text-[12px] text-text-muted">{subtitle}</div> : null}
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

