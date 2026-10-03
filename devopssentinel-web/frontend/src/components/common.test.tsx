import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ConfidenceTag,
  EmptyState,
  ErrorState,
  Freshness,
  PartialBanner,
  StatusPill,
} from "@/components/common";
import type { Envelope } from "@/types";

function envelope(overrides: Partial<Envelope<unknown>> = {}): Envelope<unknown> {
  return {
    schemaVersion: "1.0",
    toolVersion: "4.2.2",
    timestamp: "2026-10-03T00:00:00Z",
    context: "ctx",
    namespace: "ns",
    source: "LIVE",
    status: "OK",
    partial: false,
    durationMs: 742,
    cacheAgeMs: 0,
    data: null,
    warnings: [],
    errors: [],
    ...overrides,
  };
}

describe("StatusPill", () => {
  it("renders an icon glyph and a text label, never colour alone", () => {
    render(<StatusPill status="CRITICAL" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("✕")).toBeInTheDocument();
  });

  it("renders UNKNOWN for unrecognised values", () => {
    render(<StatusPill status="weird" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});

describe("Freshness", () => {
  it("labels cached data as CACHE", () => {
    render(<Freshness envelope={envelope({ source: "CACHE", cacheAgeMs: 8000 })} />);
    expect(screen.getByText(/CACHE/)).toBeInTheDocument();
  });

  it("shows duration for live data", () => {
    render(<Freshness envelope={envelope()} />);
    expect(screen.getByText(/742ms/)).toBeInTheDocument();
  });
});

describe("PartialBanner", () => {
  it("renders nothing for complete live data", () => {
    const { container } = render(<PartialBanner envelope={envelope()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("prominently flags partial data", () => {
    render(<PartialBanner envelope={envelope({ partial: true, warnings: ["16 collectors failed"] })} />);
    expect(screen.getByText("PARTIAL DATA")).toBeInTheDocument();
    expect(screen.getByText(/16 collectors failed/)).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("distinguishes EMPTY from UNAVAILABLE", () => {
    render(<EmptyState title="No rows" detail="Nothing matched." />);
    expect(screen.getByText("EMPTY")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("explains reason, impact and next safe action without a stack trace", () => {
    render(<ErrorState envelope={envelope({ errors: ["RBAC_DENIED"] })} />);
    expect(screen.getByText("Unable to retrieve data")).toBeInTheDocument();
    expect(screen.getByText("RBAC_DENIED")).toBeInTheDocument();
    expect(screen.getByText(/Next safe action/)).toBeInTheDocument();
    expect(screen.getByText("Technical details")).toBeInTheDocument();
  });
});

describe("ConfidenceTag", () => {
  it("renders the confidence vocabulary verbatim", () => {
    render(<ConfidenceTag confidence="LIKELY" />);
    expect(screen.getByText("LIKELY")).toBeInTheDocument();
  });
});
