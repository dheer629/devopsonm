import { Menu, ShieldCheck } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { breadcrumbFor, NAV_SECTIONS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useApp } from "@/state/AppContext";

/**
 * The breadcrumb band from the Kubernetes Dashboard: a solid toolbar strip with
 * a sidebar toggle, the section > page trail and a read-only marker.
 *
 * The band colour comes from `--chrome`, which is neutral in every theme except
 * `kubernetes` (indigo), so the original themes keep their existing top bar.
 */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useApp();
  const { section, trail } = breadcrumbFor(pathname);
  const sectionDef = NAV_SECTIONS.find((candidate) => candidate.label === section);

  return (
    <div className="chrome-band flex items-center gap-2 px-2.5 py-1.5">
      <button
        type="button"
        onClick={toggleSidebar}
        aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
        aria-expanded={!sidebarCollapsed}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm text-chrome-text transition-colors hover:bg-chrome-hover"
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
      </button>

      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex items-center gap-1.5 text-[13px]">
          {sectionDef ? (
            <li className="shrink-0">
              <Link
                to={sectionDef.items[0].to}
                className="text-chrome-text/80 underline-offset-2 hover:text-chrome-text hover:underline"
              >
                {section}
              </Link>
            </li>
          ) : (
            <li className="shrink-0 text-chrome-text/80">{section}</li>
          )}
          {trail.map((crumb, index) => {
            const last = index === trail.length - 1;
            return (
              <li key={`${crumb}-${index}`} className="flex min-w-0 items-center gap-1.5">
                <span aria-hidden="true" className="text-chrome-text/75">
                  ›
                </span>
                <span
                  className={cn("truncate", last ? "font-medium" : "text-chrome-text/80")}
                  aria-current={last ? "page" : undefined}
                  title={crumb}
                >
                  {crumb}
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      <span className="ml-auto hidden shrink-0 items-center gap-1 text-[11px] text-chrome-text/75 sm:flex">
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
        read-only
      </span>
    </div>
  );
}
