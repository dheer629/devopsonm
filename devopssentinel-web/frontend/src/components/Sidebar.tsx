import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { useNamespaces } from "@/api/queries";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { isActive, NAV_SECTIONS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useApp } from "@/state/AppContext";

/**
 * Sectioned navigation, mirroring the Kubernetes Dashboard: a namespace picker
 * at the top, then muted group headings with their destinations. The namespace
 * control lives here (not in the top bar) so the top bar stays a brand/search
 * strip exactly like the reference.
 */
export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, namespace, setNamespace, context } = useApp();
  const { pathname } = useLocation();
  const namespaces = useNamespaces(context);
  const namespaceList = namespaces.data?.data.namespaces ?? [];

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex shrink-0 flex-col overflow-y-auto scroll-thin border-r border-border bg-panel transition-[width]",
        sidebarCollapsed ? "w-14" : "w-56",
      )}
    >
      {!sidebarCollapsed ? (
        <div className="border-b border-border px-3 py-2">
          <div className="text-[10.5px] font-semibold uppercase tracking-wider text-text-faint">
            Namespace
          </div>
          <Select value={namespace || undefined} onValueChange={setNamespace}>
            <SelectTrigger className="mt-1 h-8 w-full" aria-label="Namespace">
              <SelectValue placeholder="Select namespace" />
            </SelectTrigger>
            <SelectContent>
              {namespaceList.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}

      <div className="flex-1 py-1">
        {NAV_SECTIONS.map((section) => (
          <div key={section.id} className="pb-0.5">
            {sidebarCollapsed ? (
              <div className="mx-2 my-1.5 border-t border-border" aria-hidden="true" />
            ) : (
              <div className="px-3 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-text-faint">
                {section.label}
              </div>
            )}
            <ul>
              {section.items.map((item) => {
                const active = isActive(item, pathname);
                return (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      title={sidebarCollapsed ? item.label : undefined}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "mx-1 flex items-center gap-2.5 rounded-sm px-2 py-1.5 text-[12.5px] transition-colors",
                        active
                          ? "bg-accent-soft font-medium text-accent"
                          : "text-text-muted hover:bg-panel-2 hover:text-text",
                      )}
                    >
                      <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      {sidebarCollapsed ? (
                        <span className="sr-only">{item.label}</span>
                      ) : (
                        <span className="truncate">{item.label}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={toggleSidebar}
        aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
        aria-expanded={!sidebarCollapsed}
        className="m-2 flex items-center justify-center gap-1 rounded-sm border border-border py-1.5 text-[11px] text-text-muted transition-colors hover:bg-panel-2 hover:text-text"
      >
        {sidebarCollapsed ? (
          <ChevronRight className="h-3.5 w-3.5" />
        ) : (
          <>
            <ChevronLeft className="h-3.5 w-3.5" /> Collapse
          </>
        )}
      </button>
    </nav>
  );
}

