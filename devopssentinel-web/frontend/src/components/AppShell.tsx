import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { CommandPalette } from "@/components/CommandPalette";
import { Inspector } from "@/components/Inspector";
import { Sidebar } from "@/components/Sidebar";
import { StatusBar } from "@/components/StatusBar";
import { TopBar } from "@/components/TopBar";

/** Enterprise operations shell: top bar, collapsible nav, inspector, status bar. */
export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const navigate = useNavigate();

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
      if (event.key === "/" && !typing) {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (event.key === "?" && !typing) {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (typing) return;

      if (event.key === "g") {
        chord = "g";
        window.clearTimeout(chordTimer);
        chordTimer = window.setTimeout(() => (chord = ""), 900);
        return;
      }
      if (chord === "g") {
        const map: Record<string, string> = {
          d: "/dashboard",
          p: "/workloads",
          g: "/gitops",
          c: "/pki",
          n: "/network",
          s: "/storage",
          f: "/findings",
          t: "/topology",
          e: "/events",
        };
        const route = map[event.key.toLowerCase()];
        if (route) {
          event.preventDefault();
          navigate(route);
        }
        chord = "";
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);

  return (
    <div className="flex h-full flex-col">
      <TopBar onOpenPalette={() => setPaletteOpen(true)} />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto scroll-thin p-3">
          <Outlet />
        </main>
        <Inspector />
      </div>
      <StatusBar />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
