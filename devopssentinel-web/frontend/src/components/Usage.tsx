import { useEffect, useRef, useState } from "react";

import { formatBytes, formatCores } from "@/lib/format";

export interface UsageSample {
  t: number;
  value: number;
}

/**
 * Keep a rolling window of samples for one scalar metric.
 *
 * Samples are appended when the envelope timestamp changes, so a live-refresh
 * tick adds exactly one point and a cached re-render adds none. The buffer is
 * large enough to hold a full day at the fastest tick, so the range selector
 * can zoom out without the history having been discarded.
 */
export function useUsageHistory(
  stamp: string | undefined,
  value: number | undefined,
  limit = 20000,
): UsageSample[] {
  const [series, setSeries] = useState<UsageSample[]>([]);
  const seen = useRef("");

  useEffect(() => {
    if (!stamp || value === undefined || seen.current === stamp) return;
    seen.current = stamp;
    const parsed = Date.parse(stamp);
    setSeries((prev) =>
      [...prev, { t: Number.isNaN(parsed) ? Date.now() : parsed, value }].slice(-limit),
    );
  }, [stamp, value, limit]);

  return series;
}

/** Selectable observation windows, from minutes to days. */
export const USAGE_RANGES = [
  { id: "1m", label: "1 min", ms: 60_000 },
  { id: "5m", label: "5 min", ms: 5 * 60_000 },
  { id: "15m", label: "15 min", ms: 15 * 60_000 },
  { id: "1h", label: "1 hour", ms: 60 * 60_000 },
  { id: "6h", label: "6 hours", ms: 6 * 60 * 60_000 },
  { id: "24h", label: "24 hours", ms: 24 * 60 * 60_000 },
  { id: "7d", label: "7 days", ms: 7 * 24 * 60 * 60_000 },
] as const;

export type UsageRangeId = (typeof USAGE_RANGES)[number]["id"];

export const DEFAULT_USAGE_RANGE: UsageRangeId = "15m";

export function usageRangeMs(id: UsageRangeId): number {
  return USAGE_RANGES.find((range) => range.id === id)?.ms ?? 15 * 60_000;
}

/**
 * Clip the collected series to one window and downsample it.
 *
 * The Metrics API only reports an *instantaneous* value, so the chart's history
 * is whatever this page has observed since it was opened. Widening the range
 * therefore never invents older data: it only re-frames and buckets what was
 * actually collected. `bucketSeries` averages equal-sized time buckets so a
 * 7-day window stays readable instead of drawing thousands of points.
 */
export function windowedSeries(
  series: UsageSample[],
  rangeMs: number,
  now: number = Date.now(),
  maxPoints = 120,
): UsageSample[] {
  const cutoff = now - rangeMs;
  const clipped = series.filter((sample) => sample.t >= cutoff);
  if (clipped.length <= maxPoints) return clipped;

  const bucket = rangeMs / maxPoints;
  const buckets = new Map<number, { sum: number; count: number; t: number }>();
  for (const sample of clipped) {
    const index = Math.floor((sample.t - cutoff) / bucket);
    const entry = buckets.get(index) ?? { sum: 0, count: 0, t: 0 };
    entry.sum += sample.value;
    entry.count += 1;
    entry.t = entry.t || sample.t;
    buckets.set(index, entry);
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, entry]) => ({ t: entry.t, value: entry.sum / entry.count }));
}

/** A labelled window selector for the usage charts. */
export function RangeSelect({
  value,
  onChange,
  label = "Range",
}: {
  value: UsageRangeId;
  onChange: (value: UsageRangeId) => void;
  label?: string;
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-[11px] text-text-muted">
      <span className="uppercase tracking-wide text-text-faint">{label}</span>
      <select
        aria-label="Metrics range"
        className="h-7 rounded-full border border-border bg-bg-elevated px-2 text-[11.5px] text-text"
        value={value}
        onChange={(event) => onChange(event.target.value as UsageRangeId)}
      >
        {USAGE_RANGES.map((range) => (
          <option key={range.id} value={range.id}>
            {range.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * A one-line, honest description of what the chart is showing: the selected
 * window, how many samples were collected and the real span they cover.
 */
export function rangeSummary(series: UsageSample[], rangeId: UsageRangeId): string {
  const range = USAGE_RANGES.find((item) => item.id === rangeId);
  const label = range?.label ?? rangeId;
  if (series.length === 0) return `${label} window · no samples yet`;
  const spanMs = series[series.length - 1].t - series[0].t;
  const span =
    spanMs < 60_000
      ? `${Math.round(spanMs / 1000)}s`
      : spanMs < 3_600_000
        ? `${Math.round(spanMs / 60_000)}m`
        : `${(spanMs / 3_600_000).toFixed(1)}h`;
  const count = series.length === 1 ? "1 sample" : `${series.length} samples`;
  return `${label} window · ${count} over ${span}`;
}

/** Inline usage bar + value, as used in the CPU / Memory table columns. */
export function UsageBar({
  value,
  max,
  label,
  color,
}: {
  value: number;
  max: number;
  label: string;
  color: string;
}) {
  const percent = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-3.5 w-10 shrink-0 overflow-hidden rounded-sm bg-panel-2" aria-hidden="true">
        <span className="block h-full rounded-sm" style={{ width: `${percent}%`, background: color }} />
      </span>
      <span className="mono shrink-0 text-[11.5px] text-text-muted">{label}</span>
    </span>
  );
}

const CHART_W = 380;
const CHART_H = 152;
const PAD = { top: 10, right: 12, bottom: 24, left: 56 };

/**
 * A Kubernetes-Dashboard style area chart: light gridlines, a filled area, the
 * peak value labelled on the y-axis and the sample window on the x-axis.
 *
 * Pure SVG with no charting dependency; the numeric axis labels carry the data,
 * so the shape is decoration rather than the only signal.
 */
export function UsageChart({
  points,
  kind,
  color,
  emptyMessage = "Collecting the first sample…",
  note,
}: {
  points: UsageSample[];
  kind: "cpu" | "memory" | "percent";
  color: string;
  emptyMessage?: string;
  /** Honest one-line caption: the selected window and the samples it covers. */
  note?: string;
}) {
  const format = (value: number) =>
    kind === "memory" ? formatBytes(value) : kind === "percent" ? `${value.toFixed(0)}%` : formatCores(value);

  if (points.length === 0) {
    return (
      <div>
        <p className="px-1 py-12 text-center text-[12px] text-text-muted">{emptyMessage}</p>
        {note ? <p className="pb-1 text-center text-[11px] text-text-faint">{note}</p> : null}
      </div>
    );
  }

  const innerW = CHART_W - PAD.left - PAD.right;
  const innerH = CHART_H - PAD.top - PAD.bottom;
  const peak = Math.max(...points.map((point) => point.value), 0);
  // A flat-zero series has no scale worth showing. Label the axis from the real
  // peak instead of inventing a ceiling, so an all-zero chart can never imply a
  // measurement that was never taken. `scale` keeps the geometry safe.
  const ceiling = peak > 0 ? peak * 1.25 : 0;
  const scale = ceiling || 1;
  const px = (index: number) =>
    PAD.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const py = (value: number) => PAD.top + innerH - (value / scale) * innerH;

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${px(index).toFixed(1)},${py(point.value).toFixed(1)}`)
    .join(" ");
  const baseline = PAD.top + innerH;
  const area = `${line} L${px(points.length - 1).toFixed(1)},${baseline} L${px(0).toFixed(1)},${baseline} Z`;
  const clock = (ms: number) =>
    new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div>
      <svg
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      className="w-full"
      role="img"
      aria-label={`Usage over time: ${points.length} samples, peak ${format(peak)}`}
    >
      {[0, 0.33, 0.66, 1].map((fraction) => {
        const y = PAD.top + fraction * innerH;
        return (
          <g key={fraction}>
            <line
              x1={PAD.left}
              x2={CHART_W - PAD.right}
              y1={y}
              y2={y}
              stroke="var(--border)"
              strokeWidth="1"
            />
            <text x={PAD.left - 6} y={y + 3.5} textAnchor="end" fontSize="9" fill="var(--text-faint)">
              {ceiling > 0 ? format(ceiling * (1 - fraction)) : fraction === 1 ? format(0) : ""}
            </text>
          </g>
        );
      })}
      <path d={area} fill={color} opacity="0.22" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {points.length === 1 ? <circle cx={px(0)} cy={py(points[0].value)} r="2.5" fill={color} /> : null}
      <text x={PAD.left} y={CHART_H - 8} fontSize="9" fill="var(--text-faint)">
        {clock(points[0].t)}
      </text>
      <text x={CHART_W - PAD.right} y={CHART_H - 8} textAnchor="end" fontSize="9" fill="var(--text-faint)">
        {clock(points[points.length - 1].t)}
      </text>
      </svg>
      {note ? (
        <p className="pt-1 text-center text-[11px] text-text-faint">{note}</p>
      ) : null}
    </div>
  );
}
