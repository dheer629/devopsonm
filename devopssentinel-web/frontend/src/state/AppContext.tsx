import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Scope } from "@/api/client";

export type ThemeMode = "dark" | "light" | "system";
export type LiveInterval = 0 | 5 | 10 | 30 | 60;

interface AppState {
  theme: ThemeMode;
  setTheme: (t: ThemeMode) => void;
  context: string;
  setContext: (c: string) => void;
  namespace: string;
  setNamespace: (n: string) => void;
  scope: Scope;
  live: LiveInterval;
  setLive: (v: LiveInterval) => void;
  liveActive: boolean;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  inspectorOpen: boolean;
  setInspectorOpen: (v: boolean) => void;
  inspectorWidth: number;
  setInspectorWidth: (w: number) => void;
  /** Currently selected resource shown in the context inspector. */
  selection: { kind: string; name: string } | null;
  setSelection: (s: { kind: string; name: string } | null) => void;
  incidentId: string | null;
  debug: boolean;
}

const AppContext = createContext<AppState | null>(null);

const LS = {
  theme: "dsweb.theme",
  context: "dsweb.context",
  namespace: "dsweb.namespace",
  live: "dsweb.live",
  sidebar: "dsweb.sidebar",
  inspectorWidth: "dsweb.inspectorWidth",
};

function readLocal(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLocal(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage disabled -- harmless */
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(
    () => readLocal(LS.theme, "dark") as ThemeMode,
  );
  const [context, setContextState] = useState(() => readLocal(LS.context, ""));
  const [namespace, setNamespaceState] = useState(() => readLocal(LS.namespace, ""));
  const [live, setLiveState] = useState<LiveInterval>(
    () => Number(readLocal(LS.live, "0")) as LiveInterval,
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => readLocal(LS.sidebar, "0") === "1",
  );
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorWidth, setInspectorWidthState] = useState(() =>
    Number(readLocal(LS.inspectorWidth, "360")),
  );
  const [selection, setSelection] = useState<{ kind: string; name: string } | null>(null);
  const [pageVisible, setPageVisible] = useState(true);

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const dark = theme === "dark" || (theme === "system" && prefersDark);
      root.classList.toggle("dark", dark);
    };
    apply();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    const onVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const setTheme = useCallback((value: ThemeMode) => {
    setThemeState(value);
    writeLocal(LS.theme, value);
  }, []);

  const setContext = useCallback((value: string) => {
    setContextState(value);
    writeLocal(LS.context, value);
  }, []);

  const setNamespace = useCallback((value: string) => {
    setNamespaceState(value);
    writeLocal(LS.namespace, value);
  }, []);

  const setLive = useCallback((value: LiveInterval) => {
    setLiveState(value);
    writeLocal(LS.live, String(value));
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      writeLocal(LS.sidebar, prev ? "0" : "1");
      return !prev;
    });
  }, []);

  const setInspectorWidth = useCallback((value: number) => {
    setInspectorWidthState(value);
    writeLocal(LS.inspectorWidth, String(value));
  }, []);

  const scope = useMemo<Scope>(() => ({ context, namespace }), [context, namespace]);

  const value = useMemo<AppState>(
    () => ({
      theme,
      setTheme,
      context,
      setContext,
      namespace,
      setNamespace,
      scope,
      live,
      setLive,
      liveActive: live > 0 && pageVisible,
      sidebarCollapsed,
      toggleSidebar,
      inspectorOpen,
      setInspectorOpen,
      inspectorWidth,
      setInspectorWidth,
      selection,
      setSelection,
      incidentId: null,
      debug: new URLSearchParams(window.location.search).get("debug") === "1",
    }),
    [
      theme,
      setTheme,
      context,
      setContext,
      namespace,
      setNamespace,
      scope,
      live,
      setLive,
      pageVisible,
      sidebarCollapsed,
      toggleSidebar,
      inspectorOpen,
      inspectorWidth,
      setInspectorWidth,
      selection,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
