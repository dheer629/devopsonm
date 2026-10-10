import { Keyboard } from "lucide-react";

import { Dialog, DialogContent } from "@/components/ui/dialog";

interface Shortcut {
  keys: string;
  action: string;
}

const GLOBAL: Shortcut[] = [
  { keys: "Ctrl / ⌘ + K", action: "Open the command palette and global search" },
  { keys: "/", action: "Open search from anywhere outside a text field" },
  { keys: "?", action: "Show this shortcut reference" },
  { keys: "r", action: "Re-read every resource on the current page" },
  { keys: "Esc", action: "Close the palette, drawer or dialog" },
];

const CHORDS: Shortcut[] = [
  { keys: "g o", action: "Overview (dashboard)" },
  { keys: "g f", action: "Findings" },
  { keys: "g w", action: "Workloads / Pods" },
  { keys: "g e", action: "Events" },
  { keys: "g t", action: "Topology / dependency graph" },
  { keys: "g g", action: "GitOps" },
  { keys: "g c", action: "PKI / TLS certificates" },
  { keys: "g n", action: "Network" },
  { keys: "g s", action: "Storage" },
  { keys: "g l", action: "Log viewer" },
  { keys: "g x", action: "Resource describe" },
  { keys: "g d", action: "Dashboard (same as g o)" },
];

const SEARCH: Shortcut[] = [
  { keys: "pod:name", action: "Restrict to Pods" },
  { keys: "svc:name", action: "Restrict to Services" },
  { keys: "cert:name", action: "Restrict to Certificates" },
  { keys: "gitops:name", action: "Restrict to GitOps objects (flux:, helm:)" },
  { keys: "pvc:name", action: "Restrict to PersistentVolumeClaims" },
  { keys: "finding:name", action: "Restrict to Findings" },
  { keys: "ns:namespace", action: "Restrict to a namespace" },
  { keys: "status:failed", action: "Restrict to a state" },
];

function Section({ title, rows }: { title: string; rows: Shortcut[] }) {
  return (
    <section className="space-y-1">
      <h3 className="text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">
        {title}
      </h3>
      <dl className="divide-y divide-border/60">
        {rows.map((row) => (
          <div key={row.keys} className="flex items-baseline justify-between gap-4 py-1">
            <dt>
              <kbd className="mono rounded-sm border border-border bg-bg-elevated px-1.5 py-0.5 text-[11px]">
                {row.keys}
              </kbd>
            </dt>
            <dd className="text-right text-[12px] text-text-muted">{row.action}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Keyboard reference (spec section 127). Opens on `?`. */
export function ShortcutHelp({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-[8%] max-h-[84vh] max-w-3xl translate-y-0 overflow-y-auto scroll-thin"
        aria-label="Keyboard shortcuts"
      >
        <div className="flex items-center gap-2 border-b border-border pb-2">
          <Keyboard className="h-4 w-4 text-text-faint" aria-hidden="true" />
          <h2 className="text-[13.5px] font-semibold text-text">Keyboard shortcuts</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Section title="Global" rows={GLOBAL} />
          <Section title="Search prefixes" rows={SEARCH} />
        </div>
        <Section title="Go to (press g, then the letter)" rows={CHORDS} />
        <p className="border-t border-border pt-2 text-[11.5px] text-text-muted">
          Every list, table and dialog is reachable without a mouse. Nothing here writes to the
          cluster — DevOpsSentinel is read-only by construction.
        </p>
      </DialogContent>
    </Dialog>
  );
}
