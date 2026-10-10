import { Command, CornerDownLeft, History, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useResourceSearch } from "@/api/queries";
import { StatusPill } from "@/components/common";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NAV_ITEMS } from "@/lib/nav";
import { pushRecent, readRecents, type RecentEntry } from "@/lib/recents";
import { useApp } from "@/state/AppContext";

interface PaletteItem {
  key: string;
  kind: string;
  name: string;
  namespace: string;
  route: string;
  state: string;
  /** Provenance shown on the right: the engine operation, or why it is listed. */
  note: string;
  group: "Commands" | "Recent" | string;
}

/** Debounce so a keystroke does not fire an engine read per character. */
function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { scope, setSelection } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [recents, setRecents] = useState<RecentEntry[]>([]);
  const listRef = useRef<HTMLUListElement>(null);

  const debounced = useDebounced(query, 250);
  const search = useResourceSearch(scope, debounced, open);
  const searching = search.isFetching;

  // Recents are read when the palette opens, not on every keystroke.
  useEffect(() => {
    if (open) setRecents(readRecents());
  }, [open]);

  const commands = useMemo<PaletteItem[]>(
    () =>
      NAV_ITEMS.map((item) => ({
        key: `cmd:${item.to}`,
        kind: "Command",
        name: item.label,
        namespace: "",
        route: item.to,
        state: "INFO",
        note: item.to,
        group: "Commands",
      })),
    [],
  );

  const recentItems = useMemo<PaletteItem[]>(
    () =>
      recents.map((row) => ({
        key: `recent:${row.kind}:${row.namespace}:${row.name}`,
        kind: row.kind,
        name: row.name,
        namespace: row.namespace,
        route: row.route,
        state: "INFO",
        note: "recent",
        group: "Recent",
      })),
    [recents],
  );

  const hits = useMemo<PaletteItem[]>(() => {
    const rows = search.data?.data.results ?? [];
    return rows.map((hit) => ({
      key: `hit:${hit.kind}:${hit.namespace}:${hit.name}`,
      kind: hit.kind,
      name: hit.name,
      namespace: hit.namespace,
      route: hit.route,
      state: hit.state,
      note: hit.engine,
      group: hit.kind,
    }));
  }, [search.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const pick = (list: PaletteItem[]) =>
      needle
        ? list.filter(
            (item) =>
              item.name.toLowerCase().includes(needle) ||
              item.kind.toLowerCase().includes(needle) ||
              item.namespace.toLowerCase().includes(needle),
          )
        : list;

    if (!needle) {
      return [...pick(recentItems).slice(0, 5), ...pick(commands)].slice(0, 60);
    }
    // With a query typed, server hits lead: they cover every domain.
    return [...pick(hits), ...pick(commands)].slice(0, 60);
  }, [query, hits, commands, recentItems]);

  useEffect(() => {
    setActive(0);
  }, [query, open, filtered.length]);

  // Keep the highlighted row in view during arrow-key navigation.
  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    node?.scrollIntoView({ block: "nearest" });
  }, [active, filtered]);

  const choose = (item: PaletteItem) => {
    if (item.kind !== "Command") {
      setSelection({ kind: item.kind, name: item.name });
      setRecents(
        pushRecent({
          kind: item.kind,
          name: item.name,
          namespace: item.namespace,
          route: item.route,
          context: scope.context ?? "",
        }),
      );
    }
    navigate(item.route);
    onOpenChange(false);
    setQuery("");
  };

  const data = search.data?.data;
  const unavailable = data?.unavailable ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-[12%] max-w-2xl translate-y-0 gap-0 overflow-hidden p-0"
        aria-label="Global search and command palette"
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search className="h-4 w-4 shrink-0 text-text-faint" aria-hidden="true" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((i) => Math.min(i + 1, filtered.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((i) => Math.max(i - 1, 0));
              } else if (event.key === "Enter" && filtered[active]) {
                event.preventDefault();
                choose(filtered[active]);
              }
            }}
            placeholder="Search resources and commands…  pod:  svc:  cert:  gitops:  pvc:  ns:  status:"
            className="border-0 bg-transparent focus-visible:outline-none"
            aria-label="Search resources and commands"
            aria-describedby="palette-hint"
          />
          {searching ? (
            <span className="shrink-0 text-[11px] text-text-muted" role="status">
              searching…
            </span>
          ) : null}
        </div>

        {/* Live status for screen readers: result count, coverage and gaps. */}
        <p id="palette-hint" className="sr-only" role="status" aria-live="polite">
          {filtered.length} results.{" "}
          {data ? `Searched ${data.searched.join(", ")}.` : "Type at least two characters."}
          {unavailable.length ? ` Unavailable: ${unavailable.join(", ")}.` : ""}
        </p>

        <ul ref={listRef} className="max-h-[52vh] overflow-y-auto scroll-thin p-1" role="listbox">
          {filtered.map((item, index) => {
            const header = index === 0 || filtered[index - 1].group !== item.group;
            return (
              <li key={item.key}>
                {header ? (
                  <div className="px-2 pb-0.5 pt-2 text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
                    {item.group === "Recent" ? (
                      <span className="inline-flex items-center gap-1">
                        <History className="h-3 w-3" aria-hidden="true" /> Recent
                      </span>
                    ) : (
                      item.group
                    )}
                  </div>
                ) : null}
                <button
                  type="button"
                  role="option"
                  data-active={index === active}
                  aria-selected={index === active}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(item)}
                  className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[12.5px] ${
                    index === active ? "bg-panel-2" : ""
                  }`}
                >
                  <span className="w-24 shrink-0 text-[10.5px] uppercase tracking-wide text-text-faint">
                    {item.kind}
                  </span>
                  <span className="mono truncate text-text">{item.name}</span>
                  {item.namespace ? (
                    <span className="shrink-0 text-[11px] text-text-muted">{item.namespace}</span>
                  ) : null}
                  <span className="ml-auto flex shrink-0 items-center gap-2">
                    {item.group !== "Commands" ? <StatusPill status={item.state} /> : null}
                    <span className="mono text-[10px] text-text-faint">{item.note}</span>
                  </span>
                </button>
              </li>
            );
          })}
          {filtered.length === 0 ? (
            <li className="px-2 py-6 text-center text-[12px] text-text-muted">
              {searching
                ? "Searching the cluster…"
                : query.trim().length >= 2
                  ? `No match for “${query.trim()}”.`
                  : "Type to search every domain, or pick a command."}
            </li>
          ) : null}
        </ul>

        <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[10.5px] text-text-faint">
          <span className="inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <kbd className="mono rounded-sm border border-border px-1">↑↓</kbd> navigate
            </span>
            <span className="inline-flex items-center gap-1">
              <kbd className="mono rounded-sm border border-border px-1">
                <CornerDownLeft className="h-2.5 w-2.5" aria-hidden="true" />
              </kbd>{" "}
              open
            </span>
            <span className="inline-flex items-center gap-1">
              <kbd className="mono rounded-sm border border-border px-1">?</kbd> shortcuts
            </span>
          </span>
          {data ? (
            <span className="mono">
              {data.total} hit{data.total === 1 ? "" : "s"} · {data.searched.length} domain
              {data.searched.length === 1 ? "" : "s"}
              {unavailable.length ? ` · ${unavailable.length} unavailable` : ""}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <Command className="h-3 w-3" aria-hidden="true" /> Ctrl K
            </span>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
