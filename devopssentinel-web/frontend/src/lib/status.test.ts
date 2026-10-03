import { describe, expect, it } from "vitest";

import { canonicalSeverityOrder, severityOf, severityRank } from "@/lib/status";
import { freshness, relative, shortTime } from "@/lib/format";

describe("status semantics", () => {
  it("maps unknown strings to UNKNOWN rather than guessing", () => {
    expect(severityOf("something-else")).toBe("UNKNOWN");
    expect(severityOf(undefined)).toBe("UNKNOWN");
    expect(severityOf(null)).toBe("UNKNOWN");
  });

  it("keeps one canonical vocabulary", () => {
    expect(severityOf("ok")).toBe("OK");
    expect(severityOf("Critical")).toBe("CRITICAL");
    expect(severityOf("failed")).toBe("FAILED");
    expect(severityOf("partial")).toBe("PARTIAL");
  });

  it("orders abnormal states before healthy ones", () => {
    expect(severityRank("FAILED")).toBeLessThan(severityRank("CRITICAL"));
    expect(severityRank("CRITICAL")).toBeLessThan(severityRank("WARNING"));
    expect(severityRank("WARNING")).toBeLessThan(severityRank("OK"));
    expect(canonicalSeverityOrder()).toContain("UNKNOWN");
  });
});

describe("freshness formatting", () => {
  it("never presents cached data as live", () => {
    expect(freshness("CACHE", 700, 8000, "2026-10-03T00:00:00Z")).toContain("CACHE");
    expect(freshness("LIVE", 742, 0, "2026-10-03T00:00:00Z")).toContain("742ms");
    expect(freshness("UNAVAILABLE", 0, 0, "")).toBe("UNAVAILABLE");
  });

  it("formats times defensively", () => {
    expect(shortTime(undefined)).toBe("--:--:--");
    expect(shortTime("not-a-date")).toBe("--:--:--");
    expect(relative(undefined)).toBe("unknown");
  });
});
