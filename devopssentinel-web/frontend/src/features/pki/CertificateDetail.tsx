import { ExternalLink, X } from "lucide-react";
import { useMemo } from "react";

import {
  useCertificateChain,
  useCertificateConsumers,
  useCertificateDetail,
} from "@/api/queries";
import {
  ConfidenceTag,
  EmptyState,
  Field,
  LoadingRows,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { severityOf } from "@/lib/status";
import { useApp } from "@/state/AppContext";

/**
 * Validity timeline (spec section 70).
 *
 * A simple remaining-life bar rather than a decorative chart, with the exact
 * dates and remaining days always stated in text so the information never
 * depends on reading a colour.
 */
function ValidityTimeline({
  notBefore,
  expiry,
  days,
}: {
  notBefore: string;
  expiry: string;
  days: number | null;
}) {
  const segments = useMemo(() => {
    if (days === null) return { tone: "var(--c-unknown)", label: "unknown" };
    if (days < 0) return { tone: "var(--c-critical)", label: "expired" };
    if (days <= 7) return { tone: "var(--c-critical)", label: "critical" };
    if (days <= 30) return { tone: "var(--c-warning)", label: "warning" };
    if (days <= 60) return { tone: "var(--c-info)", label: "notice" };
    return { tone: "var(--c-success)", label: "healthy" };
  }, [days]);

  // Where "now" sits across the certificate's own lifetime, when the engine
  // reported a notBefore. Without it we only show the remaining-life bar.
  const elapsedPct = useMemo(() => {
    if (!notBefore || !expiry) return null;
    const start = Date.parse(notBefore);
    const end = Date.parse(expiry);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
    const now = Date.now();
    return Math.max(0, Math.min(100, ((now - start) / (end - start)) * 100));
  }, [notBefore, expiry]);

  return (
    <div className="space-y-1">
      <div
        className="relative h-2 w-full overflow-hidden rounded-full bg-bg-elevated"
        role="img"
        aria-label={`Certificate is ${segments.label}. ${days ?? "unknown"} days remaining.`}
      >
        {elapsedPct === null ? (
          <div className="h-full w-full opacity-30" style={{ background: segments.tone }} />
        ) : (
          <>
            <div className="h-full opacity-30" style={{ width: `${elapsedPct}%`, background: segments.tone }} />
            <div
              className="absolute top-0 h-full w-[2px]"
              style={{ left: `${elapsedPct}%`, background: "var(--text)" }}
            />
          </>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-text-muted">
        <span className="mono">{notBefore || "issued: unknown"}</span>
        <span className={`mono ${days !== null && days <= 30 ? "text-warning" : ""}`}>
          {days === null ? "days remaining unknown" : `${days} days remaining`}
        </span>
        <span className="mono">{expiry || "expiry: unknown"}</span>
      </div>
    </div>
  );
}

/** Leaf → intermediate → root, as far as the engine reported (spec 71). */
function TrustChain({ name }: { name: string }) {
  const chain = useCertificateChain(useApp().scope, name);
  const data = chain.data?.envelope.data;
  const links = data?.chain ?? [];

  if (chain.isLoading) return <LoadingRows rows={3} />;
  if (links.length === 0) {
    return (
      <EmptyState
        title="No chain reported"
        detail="The engine reported no issuer relationship for this certificate, so no chain can be shown. Nothing is inferred."
      />
    );
  }
  return (
    <>
      <ol className="space-y-1">
        {links.map((link, index) => (
          <li
            key={`${link.subject}-${index}`}
            className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-1 last:border-0"
          >
            <Badge tone={index === 0 ? "pki" : "neutral"}>
              {index === 0 ? "LEAF" : data?.complete && index === links.length - 1 ? "ROOT" : "INTERMEDIATE"}
            </Badge>
            <span className="mono truncate text-[12px] text-text">{link.subject || "—"}</span>
            <span className="text-[11px] text-text-muted">issued by {link.issuer}</span>
            <span className="ml-auto flex items-center gap-2">
              <span className="mono text-[11px] text-text-muted">
                {link.days === null ? link.expiry || "—" : `${link.days}d`}
              </span>
              <StatusPill status={link.status} />
            </span>
          </li>
        ))}
      </ol>
      {data?.complete ? null : (
        <p className="mt-1 text-[11px] text-warning">
          Chain truncated ({data?.terminated === "cycle" ? "issuer cycle detected" : "issuer not in the inventory"}).
          The engine did not report the remaining links, so they are not drawn.
        </p>
      )}
    </>
  );
}

/** Objects that reference this certificate (spec 69). */
function Consumers({ name }: { name: string }) {
  const consumers = useCertificateConsumers(useApp().scope, name);
  const direct = consumers.data?.envelope.data?.direct ?? [];
  if (consumers.isLoading) return <LoadingRows rows={3} />;
  if (direct.length === 0) {
    return (
      <p className="text-[12px] text-text-muted">
        No object was observed referencing this certificate. That means none was found in the
        engine&apos;s dependency report — not that none exists.
      </p>
    );
  }
  return (
    <ul className="space-y-1">
      {direct.map((item) => (
        <li key={item} className="mono text-[12px] text-text">
          {item}
        </li>
      ))}
    </ul>
  );
}

/**
 * Certificate workspace (spec sections 69-72).
 *
 * A side drawer rather than a new route, so the inventory stays visible and the
 * operator can compare neighbours without losing their place.
 */
export function CertificateDetail({ name, onClose }: { name: string; onClose: () => void }) {
  const { scope } = useApp();
  const detail = useCertificateDetail(scope, name);
  const cert = detail.data?.envelope.data?.certificate ?? null;
  const warnings = detail.data?.envelope.warnings ?? [];

  return (
    <aside
      aria-label={`Certificate ${name}`}
      className="flex w-full max-w-xl shrink-0 flex-col border-l border-border bg-panel"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <Badge tone="pki">Certificate</Badge>
          <div className="mono mt-1 break-all text-[12.5px] text-text">{name}</div>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto scroll-thin p-3">
        {detail.isLoading ? <LoadingRows rows={6} /> : null}

        {warnings.map((warning) => (
          <p key={warning} className="text-[11.5px] text-warning">
            {warning}
          </p>
        ))}

        {!detail.isLoading && !cert ? (
          <EmptyState
            title="Not in the certificate inventory"
            detail="This name is not one of the certificates the engine reported. Relationships, if any, are still shown below."
          />
        ) : null}

        {cert ? (
          <>
            <section className="space-y-1">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Validity
              </h3>
              <ValidityTimeline notBefore={cert.not_before} expiry={cert.expiry} days={cert.days} />
              <div className="pt-1">
                <StatusPill status={cert.status} />
              </div>
            </section>

            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Identity
              </h3>
              <dl>
                <Field label="Common name" mono>
                  {cert.cn || "—"}
                </Field>
                <Field label="Namespace" mono>
                  {cert.namespace || "—"}
                </Field>
                <Field label="Issuer" mono>
                  {cert.issuer || "—"}
                </Field>
                <Field label="Serial" mono>
                  {cert.serial || "—"}
                </Field>
                <Field label="Fingerprint" mono>
                  {cert.fingerprint || "—"}
                </Field>
                <Field label="GitOps" mono>
                  {cert.gitops || "—"}
                </Field>
                <Field label="Observed by" mono>
                  {cert.source || "the engine"}
                </Field>
              </dl>
            </section>
          </>
        ) : null}

        {cert ? (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Subject alternative names
            </h3>
            {cert.san ? (
              <ul className="space-y-0.5">
                {cert.san
                  .split(/[,\s]+/)
                  .filter(Boolean)
                  .map((entry) => (
                    <li key={entry} className="mono text-[11.5px] text-text">
                      {entry}
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="text-[12px] text-text-muted">None reported.</p>
            )}
          </section>
        ) : null}

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Trust chain
          </h3>
          <TrustChain name={name} />
          <p className="mt-1 text-[11px] text-text-faint">
            Chain depth is limited to what the engine reported; missing links are never synthesised.
          </p>
        </section>

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Consumers
          </h3>
          <Consumers name={name} />
        </section>

        <section className="rounded-md border border-border bg-panel-2 p-2">
          <h3 className="flex flex-wrap items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Live TLS comparison
            <Badge tone="warning">ENGINE ONLY</Badge>
          </h3>
          <p className="mt-1 text-[11.5px] text-text-muted">
            Comparing the Secret against the live endpoint requires opening a TLS connection to an
            operator-supplied host. The browser adapter deliberately does not open arbitrary sockets,
            so this stays in the engine&apos;s interactive console. The Secret-side fingerprint and
            expiry above are still shown, so the comparison can be made by hand.
          </p>
          <p className="mt-1 inline-flex items-center gap-1 text-[11px] text-text-faint">
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            <span className="mono">
              devopssentinel --certificates --namespace {scope.namespace || "<namespace>"}
            </span>
          </p>
        </section>

        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Classification
          </h3>
          <dl>
            <Field label="Severity">
              <span className="mono">{severityOf(cert?.status ?? "UNKNOWN")}</span>
            </Field>
            <Field label="Confidence">
              <ConfidenceTag confidence="CONFIRMED" />
            </Field>
            <Field label="Source">
              <span className="mono">the engine&apos;s certificate report</span>
            </Field>
          </dl>
        </section>
      </div>
    </aside>
  );
}

