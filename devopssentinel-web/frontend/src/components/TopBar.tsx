import { Monitor, Moon, Search, ShieldCheck, Sun } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch, Tooltip } from "@/components/ui/primitives";
import { useContexts, useNamespaces, useSystem } from "@/api/queries";
import { useApp, type LiveInterval, type ThemeMode } from "@/state/AppContext";

const LIVE_OPTIONS: LiveInterval[] = [0, 5, 10, 30, 60];

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const {
    theme,
    setTheme,
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

  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-2">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-kubernetes" aria-hidden="true" />
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
        className="ml-2 flex h-8 min-w-[240px] flex-1 items-center gap-2 rounded-md border border-border bg-bg-elevated px-2 text-left text-[12px] text-text-faint hover:border-border-strong md:max-w-md"
        aria-label="Open global search and command palette"
      >
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="flex-1">Search resources and commands…</span>
        <kbd className="mono rounded border border-border px-1 text-[10px]">Ctrl K</kbd>
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
          <div className="flex items-center gap-1 rounded-md border border-border px-2 py-1">
            <span className="text-[11px] text-text-muted">LIVE</span>
            <Select value={String(live)} onValueChange={(v) => setLive(Number(v) as LiveInterval)}>
              <SelectTrigger className="h-5 w-[74px] border-0 bg-transparent px-1" aria-label="Live refresh interval">
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

        <div className="flex items-center gap-1 rounded-md border border-border px-2 py-1">
          <span className="text-[11px] text-text-muted">Theme</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Dark theme"
            onClick={() => setTheme("dark" as ThemeMode)}
          >
            <Moon className={theme === "dark" ? "h-3.5 w-3.5 text-accent" : "h-3.5 w-3.5"} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Light theme"
            onClick={() => setTheme("light" as ThemeMode)}
          >
            <Sun className={theme === "light" ? "h-3.5 w-3.5 text-accent" : "h-3.5 w-3.5"} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="System theme"
            onClick={() => setTheme("system" as ThemeMode)}
          >
            <Monitor className={theme === "system" ? "h-3.5 w-3.5 text-accent" : "h-3.5 w-3.5"} />
          </Button>
        </div>

        <div className="hidden items-center gap-1 xl:flex">
          <Input readOnly value={context || "no-context"} className="h-7 w-[150px] mono" aria-label="Active context" />
          <Switch checked disabled aria-hidden="true" />
        </div>
      </div>
    </header>
  );
}
