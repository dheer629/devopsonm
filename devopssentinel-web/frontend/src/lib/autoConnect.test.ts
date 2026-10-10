import { beforeEach, describe, expect, it } from "vitest";

import { isAutoConnectSuppressed, setAutoConnectSuppressed } from "./autoConnect";

describe("auto-connect suppression", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("defaults to not suppressed", () => {
    // A fresh browser should auto-connect: that is the whole point.
    expect(isAutoConnectSuppressed()).toBe(false);
  });

  it("remembers an explicit disconnect", () => {
    setAutoConnectSuppressed(true);
    expect(isAutoConnectSuppressed()).toBe(true);
  });

  it("forgets it once a connection is asked for again", () => {
    setAutoConnectSuppressed(true);
    setAutoConnectSuppressed(false);
    expect(isAutoConnectSuppressed()).toBe(false);
  });

  it("survives a reload", () => {
    // The flag lives in localStorage precisely so a reload cannot undo a
    // disconnect the operator asked for.
    setAutoConnectSuppressed(true);
    const stored = window.localStorage.getItem("dsweb.autoConnectSuppressed");
    expect(stored).toBe("1");
  });
});
