import { describe, expect, it } from "vitest";

import { isLiveKey, resolveLiveHost, fixtureSqlTarget, suggestSqlTarget } from "./live";

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

describe("suggestSqlTarget", () => {
  it("prefills the database Service the cluster actually reports", () => {
    const target = suggestSqlTarget(
      { name: "postgres", namespace: "learnalgorithm", type: "ClusterIP", port: "5432", cluster_ip: "10.102.76.185" },
      "172.18.0.2",
      "127.0.0.1",
    );
    expect(target).toEqual({
      host: "10.102.76.185",
      port: "5432",
      source: "discovered",
      serviceType: "ClusterIP",
      clusterOnly: true,
    });
  });

  it("marks a NodePort or LoadBalancer as reachable from outside the cluster", () => {
    for (const type of ["NodePort", "LoadBalancer"]) {
      const target = suggestSqlTarget({ type, port: "30432", cluster_ip: "10.0.0.1" }, "", "");
      expect(target.clusterOnly).toBe(false);
    }
  });

  it("never invents an endpoint when the cluster reports no database", () => {
    // The regression: the console used to prefill a fixture NodePort
    // (172.18.0.2:30432) and state it as fact, so every query failed against a
    // cluster that has no such Service.
    const target = suggestSqlTarget(undefined, "172.18.0.2", "127.0.0.1");
    expect(target.source).toBe("node");
    expect(target.port).toBe("");
    expect(target.serviceType).toBe("");
  });

  it("falls back to the page host when the node address is unknown", () => {
    const target = suggestSqlTarget(undefined, "", "sentinel.local");
    expect(target.host).toBe("sentinel.local");
  });

  it("tolerates whitespace and a missing type", () => {
    const target = suggestSqlTarget({ cluster_ip: "  10.0.0.5  ", port: " 5432 " }, "", "");
    expect(target.host).toBe("10.0.0.5");
    expect(target.port).toBe("5432");
    expect(target.clusterOnly).toBe(true);
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

describe("fixtureSqlTarget", () => {
  it("keeps the host and the port from the same source", () => {
    // The regression: the console filled in only the fixture's *port*, so the
    // fields showed the discovered ClusterIP with a fixture NodePort --
    // 10.102.76.185:30432 -- an endpoint that exists nowhere.
    const fixture = fixtureSqlTarget("172.18.0.2", "127.0.0.1");
    expect(fixture).toEqual({
      host: "172.18.0.2",
      port: "30432",
      source: "fixture",
      serviceType: "NodePort",
      clusterOnly: false,
    });

    const discovered = suggestSqlTarget(
      { type: "ClusterIP", port: "5432", cluster_ip: "10.102.76.185" },
      "172.18.0.2",
      "127.0.0.1",
    );
    expect(fixture.host).not.toBe(discovered.host);
    expect(fixture.port).not.toBe(discovered.port);
  });

  it("falls back to the page host when the cluster reports no node address", () => {
    expect(fixtureSqlTarget("", "sentinel.local").host).toBe("sentinel.local");
    expect(fixtureSqlTarget(undefined, "").host).toBe("127.0.0.1");
  });

  it("is never marked as reachable-only-inside-the-cluster", () => {
    expect(fixtureSqlTarget("172.18.0.2", "127.0.0.1").clusterOnly).toBe(false);
  });
});

