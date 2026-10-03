/**
 * One canonical status vocabulary for the whole application
 * (spec sections 12, 68). Colour is always paired with an icon + label.
 */
export type Severity =
  | "OK"
  | "INFO"
  | "NOTICE"
  | "WARNING"
  | "CRITICAL"
  | "FAILED"
  | "UNKNOWN"
  | "PARTIAL";

export const SEVERITY_ORDER: Record<Severity, number> = {
  FAILED: 0,
  CRITICAL: 1,
  WARNING: 2,
  NOTICE: 3,
  PARTIAL: 4,
  UNKNOWN: 5,
  INFO: 6,
  OK: 7,
};

export interface SeverityStyle {
  glyph: string;
  label: string;
  className: string;
}

export const SEVERITY: Record<Severity, SeverityStyle> = {
  OK: { glyph: "●", label: "Healthy", className: "text-success" },
  INFO: { glyph: "i", label: "Info", className: "text-info" },
  NOTICE: { glyph: "•", label: "Notice", className: "text-text-muted" },
  WARNING: { glyph: "▲", label: "Warning", className: "text-warning" },
  CRITICAL: { glyph: "✕", label: "Critical", className: "text-critical" },
  FAILED: { glyph: "✕", label: "Failed", className: "text-critical" },
  UNKNOWN: { glyph: "?", label: "Unknown", className: "text-unknown" },
  PARTIAL: { glyph: "◐", label: "Partial", className: "text-warning" },
};

export function severityOf(value: string | undefined | null): Severity {
  const v = (value ?? "").toUpperCase();
  if (v in SEVERITY) return v as Severity;
  return "UNKNOWN";
}

export function severityRank(value: string | undefined | null): number {
  return SEVERITY_ORDER[severityOf(value)];
}

/** Severities ordered from most to least severe (single source of truth). */
export function canonicalSeverityOrder(): Severity[] {
  return (Object.keys(SEVERITY_ORDER) as Severity[]).sort(
    (a, b) => SEVERITY_ORDER[a] - SEVERITY_ORDER[b],
  );
}

export type Confidence = "CONFIRMED" | "HIGH CONFIDENCE" | "LIKELY" | "POSSIBLE" | "UNKNOWN";

export const CONFIDENCE_STYLE: Record<Confidence, string> = {
  CONFIRMED: "text-success",
  "HIGH CONFIDENCE": "text-info",
  LIKELY: "text-warning",
  POSSIBLE: "text-text-muted",
  UNKNOWN: "text-unknown",
};

export const DOMAIN_COLOR: Record<string, string> = {
  kubernetes: "text-kubernetes",
  workload: "text-kubernetes",
  workloads: "text-kubernetes",
  gitops: "text-gitops",
  pki: "text-pki",
  network: "text-network",
  storage: "text-storage",
  database: "text-network",
  kafka: "text-gitops",
  etdp: "text-kubernetes",
  general: "text-text-muted",
  system: "text-text-muted",
};
