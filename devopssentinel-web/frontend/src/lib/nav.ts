import {
  Activity,
  AlertTriangle,
  Boxes,
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

/** One navigable destination. `domain` drives the icon chip colour. */
export interface NavItem {
  to: string;
  label: string;
  icon: typeof Gauge;
  domain?: string;
  /** Extra route prefixes that should keep this item highlighted. */
  match?: string[];
}

/** Grouped navigation, mirroring the Kubernetes Dashboard's section headers. */
export interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAMESPACE_SECTION_ID = "namespace";

export const NAV_SECTIONS: NavSection[] = [
  {
    id: "overview",
    label: "Overview",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: Gauge },
      { to: "/findings", label: "Findings", icon: FileWarning },
    ],
  },
  {
    id: "workloads",
    label: "Workloads",
    items: [
      { to: "/workloads", label: "Pods", icon: Boxes, domain: "kubernetes", match: ["/pods/"] },
      { to: "/events", label: "Events", icon: Activity },
      { to: "/topology", label: "Topology", icon: Waypoints },
      { to: "/etdp", label: "ETDP", icon: Layers },
    ],
  },
  {
    id: "configuration",
    label: "Configuration",
    items: [
      { to: "/gitops", label: "GitOps", icon: GitBranch, domain: "gitops" },
      { to: "/pki", label: "PKI / TLS", icon: ShieldCheck, domain: "pki" },
      { to: "/network", label: "Network", icon: Network, domain: "network" },
      { to: "/storage", label: "Storage", icon: HardDrive, domain: "storage" },
      { to: "/database", label: "Database", icon: Database },
      { to: "/kafka", label: "Kafka", icon: Radio },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      { to: "/incidents/current", label: "Incidents", icon: AlertTriangle, match: ["/incidents/"] },
      { to: "/baselines", label: "PRE / POST", icon: GitCompare },
      { to: "/evidence", label: "Evidence", icon: Server },
      { to: "/exports", label: "Exports", icon: Download },
      { to: "/doctor", label: "Doctor", icon: Stethoscope },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

/** Flat list, kept for keyboard shortcuts and anything that needs a lookup. */
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((section) => section.items);

export function isActive(item: NavItem, pathname: string): boolean {
  if (pathname === item.to || pathname.startsWith(`${item.to}/`)) return true;
  return (item.match ?? []).some((prefix) => pathname.startsWith(prefix));
}

export function sectionFor(pathname: string): NavSection | undefined {
  return NAV_SECTIONS.find((section) => section.items.some((item) => isActive(item, pathname)));
}

function titleFromPath(pathname: string): string {
  const last = pathname.split("/").filter(Boolean).pop() ?? "Overview";
  return last.replace(/[-_]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Breadcrumb trail for the chrome bar: the section plus the current page. */
export function breadcrumbFor(pathname: string): { section: string; trail: string[] } {
  const pod = /^\/workloads\/pods\/(.+)$/.exec(pathname);
  if (pod) {
    return { section: "Workloads", trail: ["Pods", decodeURIComponent(pod[1])] };
  }
  const section = sectionFor(pathname);
  const item = NAV_ITEMS.find((candidate) => isActive(candidate, pathname));
  if (section && item) return { section: section.label, trail: [item.label] };
  if (pathname === "/") return { section: "Overview", trail: ["Dashboard"] };
  return { section: "DevOpsSentinel", trail: [titleFromPath(pathname)] };
}
