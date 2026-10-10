import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { Breadcrumbs } from "@/components/Breadcrumbs";
import { CommandPalette } from "@/components/CommandPalette";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Inspector } from "@/components/Inspector";
import { LiveRefresher } from "@/components/LiveRefresher";
import { ShortcutHelp } from "@/components/ShortcutHelp";
import { Sidebar } from "@/components/Sidebar";
import { StatusBar } from "@/components/StatusBar";
import { TopBar } from "@/components/TopBar";
import { breadcrumbFor } from "@/lib/nav";

/** `g`-chord destinations (spec section 126). */
const CHORDS: Record<string, string> = {
  o: "/dashboard",
  d: "/dashboard",
  f: "/findings",
  w: "/workloads",
  p: "/workloads",
  e: "/events",
  t: "/topology",
  g: "/gitops",
  c: "/pki",
  n: "/network",
  s: "/storage",
  l: "/logs",
  x: "/describe",
  b: "/baselines",
  v: "/evidence",
  h: "/health",
  i: "/incidents/current",
};

/**
 * Enterprise operations shell: top bar, collapsible nav, inspector, status bar.
 *
 * The route outlet sits inside an `ErrorBoundary` keyed on the pathname, so a
 * failing view is contained, resets on navigation, and never takes the scope
 * selectors or the palette down with it (spec section 131).
 */
export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Browser tab title reflects the resource being inspected (spec 243).
  useEffect(() => {
    const { trail } = breadcrumbFor(location.pathname);
    const leaf = trail.at(-1) ?? "Console";
    document.title = `${leaf} · DevOpsSentinel`;
  }, [location.pathname]);

  const refreshNow = useCallback(() => {
    void queryClient.refetchQueries({ type: "active" });
  }, [queryClient]);

  useEffect(() => {
    let chord = "";
    let chordTimer: number | undefined;

    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable;

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (typing) return;

      if (event.key === "/") {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }
      // `?` is the shortcut reference, not the palette (spec section 127).
      if (event.key === "?") {
        event.preventDefault();
        setHelpOpen(true);
        return;
      }
      if (event.key === "r") {
        event.preventDefault();
        refreshNow();
        return;
      }

      if (event.key === "g") {
        chord = "g";
        window.clearTimeout(chordTimer);
        chordTimer = window.setTimeout(() => (chord = ""), 900);
        return;
      }
      if (chord === "g") {
        const route = CHORDS[event.key.toLowerCase()];
        if (route) {
          event.preventDefault();
          navigate(route);
        }
        chord = "";
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate, refreshNow]);

  return (
    <div className="flex h-full flex-col">
      <TopBar onOpenPalette={() => setPaletteOpen(true)} onOpenHelp={() => setHelpOpen(true)} />
      <Breadcrumbs />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main
          id="main"
          className="min-w-0 flex-1 overflow-y-auto scroll-thin p-3 lg:p-4"
          tabIndex={-1}
        >
          <ErrorBoundary key={location.pathname} label={breadcrumbFor(location.pathname).trail.at(-1)}>
            <Outlet />
          </ErrorBoundary>
        </main>
        <Inspector />
      </div>
      <StatusBar />
      <LiveRefresher />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ShortcutHelp open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}

