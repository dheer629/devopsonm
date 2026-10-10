import { describe, expect, it } from "vitest";

import { sameEndpoint } from "./endpoint";

describe("sameEndpoint", () => {
  it("matches the same host:port written differently", () => {
    // The real case: discovery reports a full URL, a saved override may not.
    expect(sameEndpoint("https://host.docker.internal:11259", "host.docker.internal:11259")).toBe(
      true,
    );
    expect(sameEndpoint("https://host.docker.internal:11259/", "https://host.docker.internal:11259")).toBe(
      true,
    );
    expect(sameEndpoint("HTTPS://HOST.DOCKER.INTERNAL:11259", "https://host.docker.internal:11259")).toBe(
      true,
    );
  });

  it("distinguishes different ports on the same host", () => {
    // A vcluster moves its published port when it restarts, and telling the two
    // apart is the whole point of the check.
    expect(sameEndpoint("https://host.docker.internal:11259", "https://host.docker.internal:10093")).toBe(
      false,
    );
    expect(sameEndpoint("https://host.docker.internal:19999", "https://host.docker.internal:11259")).toBe(
      false,
    );
  });

  it("distinguishes different hosts", () => {
    expect(sameEndpoint("https://172.17.0.1:11259", "https://host.docker.internal:11259")).toBe(false);
  });

  it("treats a missing port as 443, matching a Kubernetes client", () => {
    expect(sameEndpoint("https://10.0.0.1", "https://10.0.0.1:443")).toBe(true);
    expect(sameEndpoint("https://10.0.0.1", "https://10.0.0.1:6443")).toBe(false);
  });

  it("never matches an empty side", () => {
    // A missing connection must not render as "Connected" to anything.
    expect(sameEndpoint("", "https://host.docker.internal:11259")).toBe(false);
    expect(sameEndpoint("https://host.docker.internal:11259", "")).toBe(false);
    expect(sameEndpoint("", "")).toBe(false);
  });

  it("falls back to a trimmed literal compare for unparseable input", () => {
    expect(sameEndpoint("not a url/", "not a url")).toBe(true);
    expect(sameEndpoint("not a url", "other")).toBe(false);
  });
});
