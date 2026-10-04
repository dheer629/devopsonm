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
 * tick adds exactly one point and a cached re-render adds none.
 */
export function useUsageHistory(
  stamp: string | undefined,
  value: number | undefined,
  limit = 30,
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
}: {
  points: UsageSample[];
  kind: "cpu" | "memory" | "percent";
  color: string;
  emptyMessage?: string;
}) {
  const format = (value: number) =>
    kind === "memory" ? formatBytes(value) : kind === "percent" ? `${value.toFixed(0)}%` : formatCores(value);

  if (points.length === 0) {
    return <p className="px-1 py-12 text-center text-[12px] text-text-muted">{emptyMessage}</p>;
  }

  const innerW = CHART_W - PAD.left - PAD.right;
  const innerH = CHART_H - PAD.top - PAD.bottom;
  const peak = Math.max(...points.map((point) => point.value), 0);
  const ceiling = peak > 0 ? peak * 1.25 : 1;
  const px = (index: number) =>
    PAD.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const py = (value: number) => PAD.top + innerH - (value / ceiling) * innerH;

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${px(index).toFixed(1)},${py(point.value).toFixed(1)}`)
    .join(" ");
  const baseline = PAD.top + innerH;
  const area = `${line} L${px(points.length - 1).toFixed(1)},${baseline} L${px(0).toFixed(1)},${baseline} Z`;
  const clock = (ms: number) =>
    new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
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
              {format(ceiling * (1 - fraction))}
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
  );
}
