import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { PlugZap, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { useCallback, useEffect } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/primitives";
import { ThemeMenu } from "@/components/ThemeMenu";
import {
  useAutoConnectOnLoad,
  useAutoDetectConnection,
  useConnections,
  useContexts,
  useNamespaces,
  useSystem,
} from "@/api/queries";
import { useApp, type LiveInterval } from "@/state/AppContext";

const LIVE_OPTIONS: LiveInterval[] = [0, 5, 10, 30, 60];

/**
 * Cluster connection state, and the button that fixes it.
 *
 * The badge reports what is *true* rather than what is configured: the backend
 * probes the active connection and reports reachability separately from
 * presence, because a saved vcluster override goes stale when the cluster
 * restarts and the published port moves. When the connection is missing or
 * dead, this component also runs the automatic connect once per page load, so
 * the operator normally never has to press anything.
 */
function ConnectionStatus() {
  const connections = useConnections();
  const autoDetect = useAutoDetectConnection();
  const data = connections.data?.data;
  const active = data?.active ?? null;
  const health = data?.health ?? null;

  // Only ask for a connection once the backend has answered, and only when the
  // one we have is missing or unreachable.
  const needsConnection = Boolean(data) && !health?.reachable;
  useAutoConnectOnLoad(needsConnection);

  const probing = autoDetect.isPending || (Boolean(needsConnection) && connections.isFetching);

  if (!data) {
    return (
      <Badge tone="neutral" className="mono">
        CONNECTING…
      </Badge>
    );
  }

  if (health?.reachable) {
    return (
      <Tooltip
        content={`Connected to ${health.server || active?.server || "the cluster"}${
          health.serverVersion ? ` (${health.serverVersion})` : ""
        }`}
      >
        <Badge tone="ok" className="mono">
          {health.context || active?.context || "CONNECTED"}
        </Badge>
      </Tooltip>
    );
  }

  return (
    <span className="flex items-center gap-1">
      <Tooltip
        content={
          health?.configured
            ? `The saved connection is not answering: ${health.detail || health.reason}`
            : "No cluster is connected, so every cluster page is empty."
        }
      >
        <Badge tone={probing ? "info" : "critical"} className="mono">
          {probing ? "CONNECTING…" : health?.configured ? "UNREACHABLE" : "NOT CONNECTED"}
        </Badge>
      </Tooltip>
      <Button
        variant="soft"
        size="sm"
        disabled={probing}
        onClick={() => autoDetect.mutate({ force: true })}
        title="Detect a reachable cluster and connect"
      >
        <PlugZap className="h-3.5 w-3.5" aria-hidden="true" />
        Connect
      </Button>
    </span>
  );
}

export function TopBar({
  onOpenPalette,
  onOpenHelp,
}: {
  onOpenPalette: () => void;
  onOpenHelp: () => void;
}) {
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
  const queryClient = useQueryClient();
  const fetching = useIsFetching();

  // "Refresh now": one explicit re-read of everything on screen, independent of
  // the LIVE interval (which only covers the cluster-facing queries).
  const refreshNow = useCallback(() => {
    void queryClient.refetchQueries({ type: "active" });
  }, [queryClient]);

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
    <header className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft">
          <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
        </span>
        <span className="text-[13.5px] font-semibold tracking-tight">DevOpsSentinel</span>
        <Badge tone="neutral" className="mono">
          v{system.data?.data.webVersion ?? "1.0.0"}
        </Badge>
        <Badge tone="ok" title="Read-only supervision mode">
          SUPERVISION [READ ONLY]
        </Badge>
        {debug ? <Badge tone="warning">DEBUG</Badge> : null}
        <ConnectionStatus />
      </div>

      <button
        type="button"
        onClick={onOpenPalette}
        className="ml-2 flex h-9 min-w-[240px] flex-1 items-center gap-2 rounded-sm border border-border bg-bg-elevated px-3 text-left text-[12.5px] text-text-faint transition-colors hover:border-border-strong hover:text-text-muted md:max-w-xl"
        aria-label="Open global search and command palette"
      >
        <Search className="h-4 w-4" aria-hidden="true" />
        <span className="flex-1">Search resources and commands…</span>
        <kbd className="mono rounded-sm border border-border px-1.5 text-[10px]">Ctrl K</kbd>
      </button>

      <Tooltip content="Keyboard shortcuts (?)">
        <button
          type="button"
          onClick={onOpenHelp}
          aria-label="Keyboard shortcuts"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border text-[12px] text-text-muted transition-colors hover:border-border-strong hover:text-text"
        >
          ?
        </button>
      </Tooltip>

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

        <Tooltip content="Re-read every resource on this page right now">
          <button
            type="button"
            onClick={refreshNow}
            aria-label="Refresh now"
            className="flex h-7 items-center gap-1 rounded-full border border-border px-2 text-[11px] text-text-muted transition-colors hover:border-border-strong hover:text-text disabled:opacity-60"
            disabled={fetching > 0}
          >
            <RefreshCw
              className={fetching > 0 ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
              aria-hidden="true"
            />
            Refresh
          </button>
        </Tooltip>

        <ThemeMenu />
      </div>
    </header>
  );
}
