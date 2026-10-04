import { describe, expect, it } from "vitest";

import { isLiveKey, resolveLiveHost } from "./live";

describe("resolveLiveHost", () => {
  it("prefers the node address the backend discovered", () => {
    expect(resolveLiveHost("172.18.0.2", "127.0.0.1")).toBe("172.18.0.2");
    expect(resolveLiveHost("  10.0.0.7  ", "sentinel.local")).toBe("10.0.0.7");
  });

  it("falls back to the page host, then loopback", () => {
    expect(resolveLiveHost("", "sentinel.local")).toBe("sentinel.local");
    expect(resolveLiveHost(undefined, "127.0.0.1")).toBe("127.0.0.1");
    expect(resolveLiveHost(null, "   ")).toBe("127.0.0.1");
  });
});

describe("isLiveKey", () => {
  it("re-reads everything cluster-facing on a tick", () => {
    for (const key of ["pods", "workloads", "findings", "events", "metrics-pods", "topology"]) {
      expect(isLiveKey([key, "ctx", "default"])).toBe(true);
    }
  });

  it("skips identity, scope and the opt-in console probes", () => {
    for (const key of ["system", "contexts", "namespaces", "sql-console", "kafka-console"]) {
      expect(isLiveKey([key])).toBe(false);
    }
  });

  it("tolerates non-string query keys", () => {
    expect(isLiveKey(["graph", "ctx", "ns", "Pod", "web"])).toBe(true);
    expect(isLiveKey([["weird"], "x"])).toBe(true);
  });
});
