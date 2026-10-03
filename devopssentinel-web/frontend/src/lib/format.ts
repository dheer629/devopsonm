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
