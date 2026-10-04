import {
  Activity,
  AlertTriangle,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileWarning,
  Gauge,
  GitBranch,
  GitCompare,
  HardDrive,
  Layers,
  Network,
  Radio,
  Server,
  Settings,
  ShieldCheck,
  Stethoscope,
  Waypoints,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useApp } from "@/state/AppContext";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof Gauge;
  domain?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: Gauge },
  { to: "/workloads", label: "Workloads", icon: Boxes, domain: "kubernetes" },
  { to: "/events", label: "Events", icon: Activity },
  { to: "/topology", label: "Topology", icon: Waypoints },
  { to: "/gitops", label: "GitOps", icon: GitBranch, domain: "gitops" },
  { to: "/pki", label: "PKI / TLS", icon: ShieldCheck, domain: "pki" },
  { to: "/network", label: "Network", icon: Network, domain: "network" },
  { to: "/storage", label: "Storage", icon: HardDrive, domain: "storage" },
  { to: "/database", label: "Database", icon: Database },
  { to: "/kafka", label: "Kafka", icon: Radio },
  { to: "/etdp", label: "ETDP", icon: Layers },
  { to: "/findings", label: "Findings", icon: FileWarning },
  { to: "/incidents/current", label: "Incidents", icon: AlertTriangle },
  { to: "/baselines", label: "PRE / POST", icon: GitCompare },
  { to: "/evidence", label: "Evidence", icon: Server },
  { to: "/exports", label: "Exports", icon: Download },
  { to: "/doctor", label: "Doctor", icon: Stethoscope },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useApp();

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex shrink-0 flex-col border-r border-border bg-panel transition-[width]",
        sidebarCollapsed ? "w-12" : "w-52",
      )}
    >
      <ul className="flex-1 space-y-0.5 overflow-y-auto scroll-thin p-1.5">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-[12.5px] text-text-muted hover:bg-panel-2 hover:text-text",
                  isActive && "bg-panel-2 text-text",
                )
              }
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {sidebarCollapsed ? (
                <span className="sr-only">{item.label}</span>
              ) : (
                <span className="truncate">{item.label}</span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={toggleSidebar}
        aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
        aria-expanded={!sidebarCollapsed}
        className="flex items-center justify-center gap-1 border-t border-border py-1.5 text-[11px] text-text-muted hover:bg-panel-2 hover:text-text"
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
