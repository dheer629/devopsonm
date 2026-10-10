import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppProvider } from "@/state/AppContext";

import { SqlConsole } from "./SqlConsole";

/** The live cluster this defect was found on: a ClusterIP, and no NodePort. */
const DISCOVERED = {
  name: "postgres",
  namespace: "learnalgorithm",
  type: "ClusterIP",
  port: "5432",
  cluster_ip: "10.102.76.185",
  external_ip: "",
  ready_endpoint: "10.244.0.9",
  database: "UNKNOWN",
  username: "UNKNOWN",
  status: "OK",
};

function json(body: unknown): Promise<Response> {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response);
}

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppProvider>
        <SqlConsole />
      </AppProvider>
    </QueryClientProvider>,
  );
}

const value = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;

describe("SqlConsole", () => {
  beforeEach(() => {
    // jsdom has no matchMedia, and AppProvider reads the colour-scheme query.
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/database/console")) {
          return json({
            data: {
              enabled: true,
              driverAvailable: true,
              maxRows: 200,
              timeoutS: 15,
              defaultHost: "172.18.0.2",
              reason: "",
            },
          });
        }
        if (url.includes("/api/v1/database/services")) {
          return json({ envelope: { data: [DISCOVERED] }, raw: { stdout: "", stderr: "" } });
        }
        return json({});
      }),
    );
  });

  it("prefills the endpoint the cluster actually reports", async () => {
    renderConsole();
    await waitFor(() => expect(value("Database host")).toBe("10.102.76.185"));
    expect(value("Database port")).toBe("5432");
    expect(screen.queryByText(/only answers inside the cluster/)).not.toBeNull();
  });

  it("fills the fixture as a complete endpoint, never a mixture", async () => {
    // The regression: the button set only the fixture *port* and left the
    // discovered ClusterIP as the host, so the page reported
    // 10.102.76.185:30432 -- an address that exists nowhere.
    renderConsole();
    await waitFor(() => expect(value("Database host")).toBe("10.102.76.185"));

    fireEvent.click(screen.getByRole("button", { name: "Fill E2E platform fixture" }));

    expect(value("Database host")).toBe("172.18.0.2");
    expect(value("Database port")).toBe("30432");
    expect(value("Database name")).toBe("platform");
    expect(value("Database username")).toBe("platform");
  });

  it("says where the endpoint in the fields came from", async () => {
    renderConsole();
    await screen.findByText(/Prefilled from the discovered Service/);

    fireEvent.click(screen.getByRole("button", { name: "Fill E2E platform fixture" }));

    expect(screen.queryByText(/optional E2E platform fixture/)).not.toBeNull();
    // The fields no longer hold the discovered ClusterIP, so the note about it
    // must not still be shown.
    expect(screen.queryByText(/only answers inside the cluster/)).toBeNull();
    expect(screen.queryByText(/Prefilled from the discovered Service/)).toBeNull();
  });

  it("goes back to the discovered endpoint", async () => {
    renderConsole();
    await waitFor(() => expect(value("Database host")).toBe("10.102.76.185"));

    fireEvent.click(screen.getByRole("button", { name: "Fill E2E platform fixture" }));
    fireEvent.click(screen.getByRole("button", { name: "Use the discovered endpoint" }));

    expect(value("Database host")).toBe("10.102.76.185");
    expect(value("Database port")).toBe("5432");
  });

  it("keeps the host and port consistent when the operator edits one field", async () => {
    renderConsole();
    await waitFor(() => expect(value("Database host")).toBe("10.102.76.185"));

    fireEvent.change(screen.getByLabelText("Database host"), { target: { value: "127.0.0.1" } });
    expect(value("Database port")).toBe("5432");

    fireEvent.change(screen.getByLabelText("Database port"), { target: { value: "15432" } });
    expect(value("Database host")).toBe("127.0.0.1");
    // Typing an address of your own means the ClusterIP note no longer applies.
    expect(screen.queryByText(/only answers inside the cluster/)).toBeNull();
  });
});
