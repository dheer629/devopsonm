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
import {
  resolveTheme,
  DEFAULT_DARK,
  DEFAULT_LIGHT,
  SYSTEM_THEME,
  type ThemeDef,
  type ThemeKind,
} from "@/lib/themes";

export type ThemeMode = string;
export type LiveInterval = 0 | 5 | 10 | 30 | 60;

interface AppState {
  theme: ThemeMode;
  setTheme: (t: ThemeMode) => void;
  /** Concrete theme after resolving "system". */
  resolvedTheme: ThemeDef;
  themeKind: ThemeKind;
  setThemeKind: (kind: ThemeKind) => void;
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

const ALL_THEME_CLASSES = [
  "theme-midnight",
  "theme-ocean",
  "theme-nord",
  "theme-tokyo",
  "theme-graphite",
  "theme-daylight",
  "theme-solarized",
  "theme-kubernetes",
];

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
  const [theme, setThemeState] = useState<ThemeMode>(() => readLocal(LS.theme, SYSTEM_THEME));
  const [prefersDark, setPrefersDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
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
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setPrefersDark(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const resolvedTheme = useMemo(() => resolveTheme(theme, prefersDark), [theme, prefersDark]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove(...ALL_THEME_CLASSES);
    root.classList.add(`theme-${resolvedTheme.id}`);
    root.classList.toggle("dark", resolvedTheme.kind === "dark");
    root.dataset.theme = resolvedTheme.id;
  }, [resolvedTheme]);

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

  const setThemeKind = useCallback(
    (kind: ThemeKind) => {
      setTheme(kind === "dark" ? DEFAULT_DARK : DEFAULT_LIGHT);
    },
    [setTheme],
  );

  const value = useMemo<AppState>(
    () => ({
      theme,
      setTheme,
      resolvedTheme,
      themeKind: resolvedTheme.kind,
      setThemeKind,
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
      resolvedTheme,
      setThemeKind,
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
