import { Command } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCertificates, useGitOps, usePods } from "@/api/queries";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NAV_ITEMS } from "@/lib/nav";
import { useApp } from "@/state/AppContext";
import type { SearchResult } from "@/types";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { scope, setSelection } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const pods = usePods(scope, open);
  const certs = useCertificates(scope, open);
  const gitops = useGitOps(scope, open);

  const results = useMemo<SearchResult[]>(() => {
    const routes: SearchResult[] = NAV_ITEMS.map((item) => ({
      kind: "Route",
      name: item.label,
      namespace: "",
      route: item.to,
      state: "INFO",
    }));
    const podResults: SearchResult[] = (pods.data?.envelope.data ?? []).map((pod) => ({
      kind: "Pod",
      name: pod.name,
      namespace: pod.namespace,
      route: `/workloads/pods/${pod.name}`,
      state: pod.status,
    }));
    const certResults: SearchResult[] = (certs.data?.envelope.data ?? []).map((cert) => ({
      kind: "Certificate",
      name: cert.name,
      namespace: cert.namespace,
      route: `/pki?name=${cert.name}`,
      state: cert.status,
    }));
    const gitopsResults: SearchResult[] = (gitops.data?.envelope.data ?? []).map((obj) => ({
      kind: obj.kind || "GitOps",
      name: obj.name,
      namespace: obj.namespace,
      route: `/gitops?name=${obj.name}`,
      state: obj.status,
    }));
    return [...routes, ...podResults, ...certResults, ...gitopsResults];
  }, [pods.data, certs.data, gitops.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = needle
      ? results.filter(
          (item) =>
            item.name.toLowerCase().includes(needle) || item.kind.toLowerCase().includes(needle),
        )
      : results;
    return list.slice(0, 60);
  }, [query, results]);

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  const choose = (item: SearchResult) => {
    if (item.kind !== "Route") {
      setSelection({ kind: item.kind, name: item.name });
    }
    navigate(item.route);
    onOpenChange(false);
    setQuery("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[18%] max-w-xl translate-y-0" aria-label="Command palette">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Command className="h-4 w-4 text-text-faint" aria-hidden="true" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((i) => Math.min(i + 1, filtered.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((i) => Math.max(i - 1, 0));
              } else if (event.key === "Enter" && filtered[active]) {
                event.preventDefault();
                choose(filtered[active]);
              }
            }}
            placeholder="Search commands, routes, pods, certificates, GitOps objects…"
            className="border-0 bg-transparent focus-visible:outline-none"
            aria-label="Search"
          />
        </div>
        <ul className="max-h-[46vh] overflow-y-auto scroll-thin p-1" role="listbox">
          {filtered.map((item, index) => (
            <li key={`${item.kind}:${item.name}:${index}`}>
              <button
                type="button"
                role="option"
                aria-selected={index === active}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(item)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[12.5px] ${
                  index === active ? "bg-panel-2" : ""
                }`}
              >
                <span className="w-24 shrink-0 text-[11px] uppercase tracking-wide text-text-faint">
                  {item.kind}
                </span>
                <span className="mono truncate text-text">{item.name}</span>
                {item.namespace ? (
                  <span className="ml-auto shrink-0 text-[11px] text-text-muted">{item.namespace}</span>
                ) : null}
              </button>
            </li>
          ))}
          {filtered.length === 0 ? (
            <li className="px-2 py-6 text-center text-[12px] text-text-muted">No matches.</li>
          ) : null}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
