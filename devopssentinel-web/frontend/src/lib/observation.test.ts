import { describe, expect, it } from "vitest";

import { OBSERVE_INTERVAL_MS, observationNote } from "@/lib/observation";

describe("observationNote", () => {
  it("states the interval the chart is sampling at", () => {
    expect(OBSERVE_INTERVAL_MS).toBe(5_000);
    expect(observationNote(true)).toBe("observing every 5s");
  });

  it("says plainly when sampling has been stopped", () => {
    expect(observationNote(false)).toBe("observation paused");
  });

  it("never rounds a sub-second interval down to zero seconds", () => {
    expect(observationNote(true, 400)).toBe("observing every 1s");
  });
});
