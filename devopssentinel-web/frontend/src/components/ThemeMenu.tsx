import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, Monitor, Moon, Palette, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { THEMES, SYSTEM_THEME } from "@/lib/themes";
import { cn } from "@/lib/utils";
import { useApp } from "@/state/AppContext";

function Swatch({ colors }: { colors: [string, string, string] }) {
  return (
    <span className="flex h-4 w-7 shrink-0 overflow-hidden rounded-full border border-border">
      {colors.map((color) => (
        <span key={color} className="h-full flex-1" style={{ background: color }} />
      ))}
    </span>
  );
}

/** Theme chooser: quick dark/light toggle plus the full palette list. */
export function ThemeMenu() {
  const { theme, setTheme, resolvedTheme, themeKind, setThemeKind } = useApp();

  return (
    <div className="flex items-center gap-0.5 rounded-full border border-border bg-panel-2/70 p-0.5">
      <Button
        variant="ghost"
        size="icon"
        className={cn("h-6 w-6 rounded-full", themeKind === "dark" && "bg-accent-soft text-accent")}
        aria-label="Use dark theme"
        title="Dark themes"
        onClick={() => setThemeKind("dark")}
      >
        <Moon className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className={cn("h-6 w-6 rounded-full", themeKind === "light" && "bg-accent-soft text-accent")}
        aria-label="Use light theme"
        title="Light themes"
        onClick={() => setThemeKind("light")}
      >
        <Sun className="h-3.5 w-3.5" />
      </Button>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label="Choose theme"
            title={`Theme: ${theme === SYSTEM_THEME ? "System" : resolvedTheme.label}`}
            className="inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-[11px] text-text-muted hover:bg-panel-2 hover:text-text"
          >
            <Palette className="h-3.5 w-3.5" />
            <Swatch colors={resolvedTheme.swatch} />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={8}
            className="surface-raised z-50 w-64 p-1.5"
          >
            <DropdownMenu.Label className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-faint">
              Interface theme
            </DropdownMenu.Label>

            <DropdownMenu.Item
              onSelect={() => setTheme(SYSTEM_THEME)}
              className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-[12px] text-text outline-none data-[highlighted]:bg-panel-2"
            >
              <Monitor className="h-3.5 w-3.5 text-text-muted" />
              <span className="flex-1">Follow system</span>
              {theme === SYSTEM_THEME ? <Check className="h-3.5 w-3.5 text-accent" /> : null}
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="my-1 h-px bg-border" />

            {THEMES.map((item) => (
              <DropdownMenu.Item
                key={item.id}
                onSelect={() => setTheme(item.id)}
                className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-[12px] text-text outline-none data-[highlighted]:bg-panel-2"
              >
                <Swatch colors={item.swatch} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate">{item.label}</span>
                  <span className="truncate text-[10.5px] text-text-faint">{item.hint}</span>
                </span>
                <span className="shrink-0 text-[9.5px] uppercase tracking-wide text-text-faint">
                  {item.kind}
                </span>
                {theme === item.id ? <Check className="h-3.5 w-3.5 shrink-0 text-accent" /> : null}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
