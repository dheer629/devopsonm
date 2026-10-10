import { describe, expect, it } from "vitest";

import { formatBytes, formatCores, reportText } from "./format";

describe("formatCores", () => {
  it("renders millicores the way kubectl top does", () => {
    expect(formatCores(0)).toBe("0");
    expect(formatCores(15)).toBe("0.015");
    expect(formatCores(140)).toBe("0.140");
    expect(formatCores(1500)).toBe("1.50");
  });

  it("keeps very small values visible instead of rounding them to zero", () => {
    expect(formatCores(3)).toBe("0.003");
    expect(formatCores(0.4)).toBe("0.0004");
    expect(formatCores(0.01)).toBe("<0.0001");
  });

  it("treats missing values as zero", () => {
    expect(formatCores(Number.NaN)).toBe("0");
    expect(formatCores(-5)).toBe("0");
  });
});

describe("formatBytes", () => {
  it("uses binary suffixes with three decimals below 100", () => {
    expect(formatBytes(19.746 * 1024 ** 2)).toBe("19.746 Mi");
    expect(formatBytes(1.234 * 1024 ** 3)).toBe("1.234 Gi");
    expect(formatBytes(58 * 1024 ** 2)).toBe("58.000 Mi");
  });

  it("drops decimals once the value is large", () => {
    expect(formatBytes(644 * 1024 ** 2)).toBe("644 Mi");
    expect(formatBytes(512 * 1024)).toBe("512 Ki");
  });

  it("handles zero and tiny values", () => {
    expect(formatBytes(0)).toBe("0");
    expect(formatBytes(-5)).toBe("0");
    expect(formatBytes(512)).toBe("512 B");
  });

  it("rounds the fractional values that chart tick interpolation produces", () => {
    expect(formatBytes(0.6699999999999999)).toBe("0.67 B");
    expect(formatBytes(0.33999999999999997)).toBe("0.34 B");
  });
});

describe("reportText", () => {
  it("tolerates a plain string, a lines array and junk", () => {
    expect(reportText("a\nb")).toBe("a\nb");
    expect(reportText({ title: "t", lines: ["a", "b"] })).toBe("a\nb");
    expect(reportText(null)).toBe("");
    expect(reportText(42)).toBe("");
  });
});
