import { Search, ShieldCheck } from "lucide-react";
import { useEffect } from "react";

import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/primitives";
import { ThemeMenu } from "@/components/ThemeMenu";
import { useContexts, useNamespaces, useSystem } from "@/api/queries";
import { useApp, type LiveInterval } from "@/state/AppContext";

const LIVE_OPTIONS: LiveInterval[] = [0, 5, 10, 30, 60];

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const {
    context,
    setContext,
    namespace,
    setNamespace,
    live,
    setLive,
    debug,
  } = useApp();
  const system = useSystem();
  const contexts = useContexts();
  const namespaces = useNamespaces(context);

  const contextList = contexts.data?.data.contexts ?? [];
  const namespaceList = namespaces.data?.data.namespaces ?? [];

  // First run: adopt the kubeconfig's current context so the workspace is
  // immediately scoped instead of showing an empty selector.
  const current = contexts.data?.data.current;
  useEffect(() => {
    if (!context && current) setContext(current);
  }, [context, current, setContext]);

  // The engine requires a namespace in non-interactive mode, so adopt a
  // sensible default (prefer `default`) once the list is available. Without
  // this every domain page reports "namespace is required" and looks empty.
  // A stale stored value that no longer exists is replaced too.
  useEffect(() => {
    if (namespaceList.length === 0) return;
    if (namespace && namespaceList.includes(namespace)) return;
    const preferred = namespaceList.includes("default") ? "default" : namespaceList[0];
    setNamespace(preferred);
  }, [namespace, namespaceList, setNamespace]);

  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-border/80 bg-panel/85 px-3 py-2 backdrop-blur-xl">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft">
          <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
        </span>
        <span className="text-[13px] font-semibold tracking-tight">DevOpsSentinel</span>
        <Badge tone="neutral" className="mono">
          v{system.data?.data.webVersion ?? "1.0.0"}
        </Badge>
        <Badge tone="ok" title="Read-only supervision mode">
          SUPERVISION [READ ONLY]
        </Badge>
        {debug ? <Badge tone="warning">DEBUG</Badge> : null}
      </div>

      <button
        type="button"
        onClick={onOpenPalette}
        className="ml-2 flex h-8 min-w-[240px] flex-1 items-center gap-2 rounded-full border border-border bg-bg-elevated px-3 text-left text-[12px] text-text-faint transition-colors hover:border-border-strong hover:text-text-muted md:max-w-md"
        aria-label="Open global search and command palette"
      >
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="flex-1">Search resources and commands…</span>
        <kbd className="mono rounded-full border border-border px-1.5 text-[10px]">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-[11px] text-text-muted">
          <span className="sr-only">Kubernetes context</span>
          <Select value={context || undefined} onValueChange={setContext}>
            <SelectTrigger className="h-7 w-[190px]" aria-label="Kubernetes context">
              <SelectValue placeholder={contexts.data?.data.current || "Select context"} />
            </SelectTrigger>
            <SelectContent>
              {contextList.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="flex items-center gap-1 text-[11px] text-text-muted">
          <span className="sr-only">Namespace</span>
          <Select value={namespace || undefined} onValueChange={setNamespace}>
            <SelectTrigger className="h-7 w-[190px]" aria-label="Namespace">
              <SelectValue placeholder={namespace || "Select namespace"} />
            </SelectTrigger>
            <SelectContent>
              {namespaceList.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <Tooltip content="Live refresh interval (never below 5 seconds)">
          <div className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
            <span className="text-[11px] text-text-muted">LIVE</span>
            <Select value={String(live)} onValueChange={(v) => setLive(Number(v) as LiveInterval)}>
              <SelectTrigger className="h-6 w-[78px] border-0 bg-transparent px-1" aria-label="Live refresh interval">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LIVE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={String(option)}>
                    {option === 0 ? "OFF" : `${option} sec`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </Tooltip>

        <ThemeMenu />
      </div>
    </header>
  );
}
