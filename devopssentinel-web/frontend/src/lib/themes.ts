/**
 * Theme registry. Each theme maps to a `.theme-<id>` class defined in
 * index.css which overrides the semantic CSS variables. `kind` drives the
 * `dark` class so Tailwind's `dark:` variants and native form controls follow.
 */
export type ThemeKind = "dark" | "light";

export interface ThemeDef {
  id: string;
  label: string;
  kind: ThemeKind;
  hint: string;
  /** [background, panel, accent] used for the picker swatch. */
  swatch: [string, string, string];
}

export const SYSTEM_THEME = "system";

export const THEMES: ThemeDef[] = [
  {
    id: "midnight",
    label: "Midnight",
    kind: "dark",
    hint: "Default graphite operations theme",
    swatch: ["#080b10", "#111722", "#4c9aff"],
  },
  {
    id: "ocean",
    label: "Ocean",
    kind: "dark",
    hint: "Deep blue, high-contrast telemetry",
    swatch: ["#04121c", "#082334", "#38bdf8"],
  },
  {
    id: "nord",
    label: "Nord",
    kind: "dark",
    hint: "Muted arctic palette",
    swatch: ["#242933", "#2e3440", "#88c0d0"],
  },
  {
    id: "tokyo",
    label: "Tokyo",
    kind: "dark",
    hint: "Night-city violet and cyan",
    swatch: ["#16161e", "#1f2335", "#7aa2f7"],
  },
  {
    id: "graphite",
    label: "Graphite",
    kind: "light",
    hint: "Neutral light for bright rooms",
    swatch: ["#eef1f6", "#ffffff", "#0b6bcb"],
  },
  {
    id: "daylight",
    label: "Daylight",
    kind: "light",
    hint: "Cool light with strong separation",
    swatch: ["#eaeff7", "#ffffff", "#2563eb"],
  },
  {
    id: "solarized",
    label: "Solarized",
    kind: "light",
    hint: "Warm low-glare paper tone",
    swatch: ["#fbf4e4", "#fffdf6", "#2077b4"],
  },
  {
    id: "kubernetes",
    label: "Kubernetes",
    kind: "light",
    hint: "Kubernetes Dashboard: flat white cards, indigo toolbar",
    swatch: ["#f5f5f5", "#ffffff", "#3f51b5"],
  },
];

const BY_ID = new Map(THEMES.map((theme) => [theme.id, theme]));

export const DEFAULT_DARK = "midnight";
export const DEFAULT_LIGHT = "kubernetes";

/** Resolve the concrete theme for a stored preference (may be "system"). */
export function resolveTheme(theme: string, prefersDark: boolean): ThemeDef {
  if (theme === SYSTEM_THEME) {
    return BY_ID.get(prefersDark ? DEFAULT_DARK : DEFAULT_LIGHT) as ThemeDef;
  }
  return BY_ID.get(theme) ?? (BY_ID.get(DEFAULT_DARK) as ThemeDef);
}

export function themeById(id: string): ThemeDef | undefined {
  return BY_ID.get(id);
}
