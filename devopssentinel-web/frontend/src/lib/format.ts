import { format, formatDistanceToNow } from "date-fns";

export function shortTime(iso: string | number | undefined): string {
  if (!iso) return "--:--:--";
  const date = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return format(date, "HH:mm:ss");
}

export function relative(iso: string | number | undefined): string {
  if (!iso) return "unknown";
  const date = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown";
  return formatDistanceToNow(date, { addSuffix: true });
}

export function freshness(source: string, durationMs: number, cacheAgeMs: number, timestamp: string): string {
  const when = shortTime(timestamp);
  if (source === "CACHE") return `CACHE • ${Math.round(cacheAgeMs / 1000)}s old`;
  if (source === "LOCAL") return `LOCAL • ${when}`;
  if (source === "UNAVAILABLE") return "UNAVAILABLE";
  return `${source} • ${durationMs}ms • updated ${when}`;
}

export function pct(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

export function truncateId(value: string, max = 28): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

/**
 * Render an engine report payload as plain text.
 *
 * Report operations without a typed normalizer return the engine's report as a
 * string. Older envelopes (and a few fixtures) wrap it as `{ title, lines }`,
 * so tolerate both shapes instead of throwing and blanking the page.
 */
export function reportText(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const lines = (data as { lines?: unknown }).lines;
    if (Array.isArray(lines)) return lines.map((line) => String(line)).join("\n");
  }
  return "";
}

/** Kubernetes-style decimal suffixes, so the columns read like `kubectl top`. */
function suffixDigits(value: number): number {
  return value >= 100 ? 0 : 3;
}

/** Millicores -> cores, e.g. `140` -> "0.140", `0` -> "0". */
export function formatCores(millicores: number): string {
  const cores = (millicores || 0) / 1000;
  if (!Number.isFinite(cores) || cores <= 0) return "0";
  if (cores >= 1) return cores.toFixed(2);
  if (cores >= 0.001) return cores.toFixed(3);
  const tiny = cores.toFixed(4);
  return tiny === "0.0000" ? "<0.0001" : tiny;
}

/** Bytes -> `19.746 Mi`, `644 Mi`, `1.234 Gi`. */
export function formatBytes(bytes: number): string {
  const value = bytes || 0;
  if (value <= 0) return "0";
  const units: [number, string][] = [
    [1024 ** 4, "Ti"],
    [1024 ** 3, "Gi"],
    [1024 ** 2, "Mi"],
    [1024, "Ki"],
  ];
  for (const [limit, suffix] of units) {
    if (value >= limit) {
      const scaled = value / limit;
      return `${scaled.toFixed(suffixDigits(scaled))} ${suffix}`;
    }
  }
  return `${value} B`;
}
