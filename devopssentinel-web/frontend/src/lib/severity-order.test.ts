import { describe, expect, it } from "vitest";

import { canonicalSeverityOrder } from "@/lib/status";

describe("severity order table", () => {
  it("includes the full documented vocabulary in severity order", () => {
    const keys = canonicalSeverityOrder();
    for (const key of ["FAILED", "CRITICAL", "WARNING", "NOTICE", "UNKNOWN", "INFO", "OK"]) {
      expect(keys).toContain(key);
    }
    expect(keys[0]).toBe("FAILED");
    expect(keys[keys.length - 1]).toBe("OK");
  });
});

