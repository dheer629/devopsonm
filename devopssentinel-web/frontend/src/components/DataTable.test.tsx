import { render, screen } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it } from "vitest";

import { DataTable } from "@/components/DataTable";

interface Row {
  name: string;
  status: string;
  restarts: number;
}

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "status", header: "Status" },
  { accessorKey: "restarts", header: "Restarts" },
];

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    name: `pod-${index}`,
    status: index % 3 === 0 ? "CRITICAL" : "OK",
    restarts: index,
  }));
}

describe("DataTable", () => {
  it("renders headers and the row counter", () => {
    render(<DataTable data={makeRows(5)} columns={columns} height={200} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("5 / 5")).toBeInTheDocument();
  });

  it("shows an explicit empty message instead of a blank table", () => {
    render(
      <DataTable data={[]} columns={columns} emptyMessage="No pods found." height={200} />,
    );
    expect(screen.getByText("No pods found.")).toBeInTheDocument();
  });

  it("virtualizes large inventories (does not render every row)", () => {
    const { container } = render(<DataTable data={makeRows(5000)} columns={columns} height={300} />);
    const rendered = container.querySelectorAll("tbody tr").length;
    expect(rendered).toBeLessThan(200);
  });
});
