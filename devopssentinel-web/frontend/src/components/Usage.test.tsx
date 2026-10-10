import { render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  rangeSummary,
  UsageChart,
  useUsageHistory,
  windowedSeries,
  type UsageSample,
} from "@/components/Usage";

const axisLabels = (container: HTMLElement): string[] =>
  Array.from(container.querySelectorAll("svg text")).map((node) => node.textContent ?? "");

describe("useUsageHistory", () => {
  it("records a sample only when a value was actually measured", () => {
    const { result, rerender } = renderHook(
      ({ stamp, value }: { stamp: string; value: number | undefined }) =>
        useUsageHistory(stamp, value),
      { initialProps: { stamp: "2026-10-10T01:00:00Z", value: undefined as number | undefined } },
    );

    // An UNAVAILABLE metrics envelope still carries a timestamp. Passing a value
    // through regardless would append a zero nobody measured.
    expect(result.current).toEqual([]);

    rerender({ stamp: "2026-10-10T01:00:01Z", value: 5 });
    expect(result.current).toEqual([{ t: Date.parse("2026-10-10T01:00:01Z"), value: 5 }]);
  });

  it("adds exactly one point per new timestamp", () => {
    const { result, rerender } = renderHook(
      ({ stamp }: { stamp: string }) => useUsageHistory(stamp, 7),
      { initialProps: { stamp: "2026-10-10T01:00:00Z" } },
    );
    expect(result.current).toHaveLength(1);

    rerender({ stamp: "2026-10-10T01:00:00Z" });
    expect(result.current).toHaveLength(1);

    rerender({ stamp: "2026-10-10T01:00:05Z" });
    expect(result.current).toHaveLength(2);
  });
});

describe("rangeSummary", () => {
  it("says plainly when nothing has been collected", () => {
    expect(rangeSummary([], "15m")).toBe("15 min window · no samples yet");
  });

  it("uses the singular for a single sample", () => {
    const one: UsageSample[] = [{ t: Date.parse("2026-10-10T01:00:00Z"), value: 0 }];
    expect(rangeSummary(one, "15m")).toBe("15 min window · 1 sample over 0s");
  });

  it("reports the real span of the samples it covers", () => {
    const base = Date.parse("2026-10-10T01:00:00Z");
    const three: UsageSample[] = [
      { t: base, value: 1 },
      { t: base + 60_000, value: 2 },
      { t: base + 120_000, value: 3 },
    ];
    expect(rangeSummary(three, "15m")).toBe("15 min window · 3 samples over 2m");
  });
});

describe("UsageChart", () => {
  it("shows the empty message instead of drawing an axis when there is no data", () => {
    render(
      <UsageChart
        points={[]}
        kind="memory"
        color="#000"
        emptyMessage="Metrics API unavailable — install metrics-server to chart live usage."
        note="15 min window · no samples yet"
      />,
    );
    expect(screen.getByText(/Metrics API unavailable/)).toBeInTheDocument();
    expect(screen.getByText("15 min window · no samples yet")).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("falls back to the collecting message while the first sample is pending", () => {
    render(<UsageChart points={[]} kind="cpu" color="#000" />);
    expect(screen.getByText("Collecting the first sample…")).toBeInTheDocument();
  });

  it("never fabricates a ceiling for an all-zero series", () => {
    const { container } = render(
      <UsageChart points={[{ t: Date.parse("2026-10-10T01:00:00Z"), value: 0 }]} kind="memory" color="#000" />,
    );
    // A flat zero has no scale. The axis must read 0 rather than inventing a
    // ceiling of 1 and labelling it "1 B" / "0.67 B".
    const labels = axisLabels(container).filter(Boolean);
    expect(labels).toContain("0");
    for (const label of labels) {
      expect(label).not.toMatch(/\d\.\d/);
    }
  });

  it("still scales a real series to its peak", () => {
    const { container } = render(
      <UsageChart
        points={[
          { t: Date.parse("2026-10-10T01:00:00Z"), value: 500 },
          { t: Date.parse("2026-10-10T01:00:05Z"), value: 1000 },
        ]}
        kind="cpu"
        color="#000"
      />,
    );
    expect(axisLabels(container)).toContain("1.25");
  });
});

describe("windowedSeries", () => {
  it("clips to the window without inventing older data", () => {
    const now = Date.parse("2026-10-10T01:00:00Z");
    const series: UsageSample[] = [
      { t: now - 30 * 60_000, value: 9 },
      { t: now - 60_000, value: 4 },
      { t: now, value: 5 },
    ];
    expect(windowedSeries(series, 15 * 60_000, now)).toEqual([
      { t: now - 60_000, value: 4 },
      { t: now, value: 5 },
    ]);
  });
});
