import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronsUpDown, Download, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  rowHeight?: number;
  height?: number;
  globalFilter?: string;
  onGlobalFilterChange?: (v: string) => void;
  onRowClick?: (row: T) => void;
  exportName?: string;
  emptyMessage?: string;
  initialSorting?: SortingState;
}

/**
 * Virtualized table engine (spec sections 54-55). Renders only the visible
 * window, so 1,000+ row inventories stay responsive.
 */
export function DataTable<T>({
  data,
  columns,
  rowHeight = 36,
  height = 560,
  globalFilter,
  onGlobalFilterChange,
  onRowClick,
  exportName,
  emptyMessage = "No rows.",
  initialSorting = [],
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [filter, setFilter] = useState("");
  const parentRef = useRef<HTMLDivElement>(null);

  const effectiveFilter = globalFilter ?? filter;
  const setFilterValue = onGlobalFilterChange ?? setFilter;

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility, globalFilter: effectiveFilter },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: (updater) => {
      const next = typeof updater === "function" ? updater(effectiveFilter) : updater;
      setFilterValue(String(next ?? ""));
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: "includesString",
  });

  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });

  const exportCsv = useMemo(() => {
    if (!exportName) return null;
    return () => {
      const visible = table.getAllLeafColumns().filter((c) => c.getIsVisible());
      const header = visible.map((c) => c.id).join(",");
      const body = rows
        .map((row) =>
          visible.map((c) => `"${String(row.getValue(c.id) ?? "").replace(/"/g, '""')}"`).join(","),
        )
        .join("\n");
      const blob = new Blob([`${header}\n${body}`], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${exportName}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    };
  }, [exportName, rows, table]);

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const paddingTop = virtualItems[0]?.start ?? 0;
  const paddingBottom = totalSize - (virtualItems.at(-1)?.end ?? 0);

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
        <div className="relative w-64 max-w-[50%]">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-faint"
            aria-hidden="true"
          />
          <Input
            aria-label="Filter rows"
            value={effectiveFilter}
            onChange={(event) => setFilterValue(event.target.value)}
            placeholder="Filter…"
            className="pl-7"
          />
        </div>
        <span className="mono text-[11px] text-text-muted">
          {rows.length} / {data.length}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {exportCsv ? (
            <Button variant="ghost" size="sm" onClick={exportCsv}>
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
          ) : null}
        </div>
      </div>
      <div
        ref={parentRef}
        className="scroll-thin overflow-auto"
        style={{ height }}
        role="region"
        aria-label="Data table"
      >
        <table className="min-w-full border-collapse text-[12px]">
          <thead className="sticky top-0 z-10 bg-panel-2">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"
                      }
                      className="border-b border-border px-3 py-2 text-left text-[12px] font-medium text-text-muted"
                    >
                      {header.column.getCanSort() ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 transition-colors hover:text-text"
                          onClick={header.column.getToggleSortingHandler()}
                          title={`Sort by ${header.column.id}`}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sorted === "asc" ? <ArrowUp className="h-3 w-3" aria-hidden="true" /> : null}
                          {sorted === "desc" ? <ArrowDown className="h-3 w-3" aria-hidden="true" /> : null}
                          {sorted === false ? (
                            <ChevronsUpDown className="h-3 w-3 opacity-45" aria-hidden="true" />
                          ) : null}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={table.getAllLeafColumns().length}
                  className="px-3 py-8 text-center text-text-muted"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              <>
                <tr style={{ height: paddingTop }} aria-hidden="true" />
                {virtualItems.map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  return (
                    <tr
                      key={row.id}
                      tabIndex={0}
                      onClick={() => onRowClick?.(row.original)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") onRowClick?.(row.original);
                      }}
                      className={cn(
                        "border-b border-border/60 hover:bg-panel-2",
                        onRowClick && "cursor-pointer",
                      )}
                      style={{ height: rowHeight }}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="truncate px-3 py-1 align-middle">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                <tr style={{ height: paddingBottom }} aria-hidden="true" />
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

