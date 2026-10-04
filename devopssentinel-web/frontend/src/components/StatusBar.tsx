import { Lock, Wifi, WifiOff } from "lucide-react";

import { useSystem } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { useApp } from "@/state/AppContext";

export function StatusBar() {
  const { context, namespace, live, liveActive, debug, resolvedTheme } = useApp();
  const system = useSystem();
  const data = system.data?.data;
  const connected = Boolean(data?.engineAvailable && data?.bashAvailable);

  return (
    <footer className="flex flex-wrap items-center gap-3 border-t border-border/80 bg-panel/85 px-3 py-1.5 text-[11px] text-text-muted backdrop-blur-xl">
      <span className="inline-flex items-center gap-1">
        {connected ? (
          <Wifi className="h-3 w-3 text-success" aria-hidden="true" />
        ) : (
          <WifiOff className="h-3 w-3 text-critical" aria-hidden="true" />
        )}
        <span>{connected ? "CONNECTED" : "DISCONNECTED"}</span>
      </span>
      <span className="inline-flex items-center gap-1">
        <Lock className="h-3 w-3 text-success" aria-hidden="true" />
        <span>READ ONLY</span>
      </span>
      <span>
        Context <span className="mono text-text">{context || "—"}</span>
      </span>
      <span>
        Namespace <span className="mono text-text">{namespace || "—"}</span>
      </span>
      <span>
        Engine <span className="mono text-text">{data?.engineAvailable ? "READY" : "MISSING"}</span>
      </span>
      <span>
        API schema <span className="mono text-text">{data?.apiSchema ?? "1.0"}</span>
      </span>
      <span className="ml-auto inline-flex items-center gap-2">
        <Badge tone={liveActive ? "ok" : "neutral"}>
          {live === 0 ? "LIVE OFF" : liveActive ? `LIVE ${live}s` : `LIVE ${live}s PAUSED`}
        </Badge>
        <Badge tone="accent">{resolvedTheme.label}</Badge>
        {debug ? <span className="mono">debug</span> : null}
      </span>
    </footer>
  );
}
