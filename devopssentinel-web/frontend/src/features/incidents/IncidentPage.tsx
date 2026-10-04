import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useAddNote,
  useEvidenceFiles,
  useFindings,
  useNotes,
  usePins,
  useSystem,
} from "@/api/queries";
import {
  EmptyState,
  Freshness,
  LoadingRows,
  PageHeader,
  StatusPill,
} from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { exportUrl } from "@/api/client";
import { relative } from "@/lib/format";
import { useApp } from "@/state/AppContext";

export function IncidentPage() {
  const { id = "" } = useParams();
  const { scope } = useApp();
  const system = useSystem();
  const notes = useNotes(id);
  const addNote = useAddNote();
  const evidence = useEvidenceFiles(id);
  const findings = useFindings(scope);
  const pins = usePins();
  const [draft, setDraft] = useState("");

  const incidentId = id || system.data?.data.incidentId || "";

  const submit = () => {
    const text = draft.trim();
    if (!text || !incidentId) return;
    addNote.mutate(
      { incident_id: incidentId, text },
      {
        onSuccess: () => {
          setDraft("");
          void notes.refetch();
        },
      },
    );
  };

  const criticalFindings = (findings.data?.envelope.data ?? []).filter(
    (finding) => finding.severity === "CRITICAL" || finding.severity === "FAILED",
  );

  return (
    <div className="space-y-3">
      <PageHeader
        title={incidentId ? `Incident ${incidentId}` : "Incident workspace"}
        subtitle={
          <>
            Local workspace · context <span className="mono">{scope.context || "—"}</span> ·
            namespace <span className="mono">{scope.namespace || "—"}</span>
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="warning">INCIDENT MODE</Badge>
            {findings.data ? <Freshness envelope={findings.data.envelope} /> : null}
          </div>
        }
      />

      {!incidentId ? (
        <EmptyState
          kind="UNAVAILABLE"
          title="No incident selected"
          detail="Start the launcher with --incident INC12345, or open /incidents/INC12345 directly."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Operator notes</CardTitle>
              <Badge tone="neutral">{notes.data?.data.length ?? 0} local</Badge>
            </CardHeader>
            <CardBody className="space-y-2">
              <div className="flex gap-2">
                <Input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") submit();
                  }}
                  placeholder="Record an observation…"
                  aria-label="New incident note"
                />
                <Button onClick={submit} disabled={!draft.trim() || addNote.isPending}>
                  Add
                </Button>
              </div>
              {notes.isLoading ? <LoadingRows rows={3} /> : null}
              {(notes.data?.data ?? []).length === 0 && !notes.isLoading ? (
                <p className="text-[12px] text-text-muted">
                  Notes stay on this workstation under <span className="mono">~/.devopssentinel-web</span>.
                  They are never uploaded.
                </p>
              ) : (
                <ul className="space-y-1">
                  {(notes.data?.data ?? []).map((note) => (
                    <li key={note.id} className="rounded border border-border px-2 py-1">
                      <div className="text-[12px] text-text">{note.text}</div>
                      <div className="text-[11px] text-text-faint">
                        {note.author} · {relative(note.at)}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Evidence bundles</CardTitle>
              <Badge tone="neutral">{evidence.data?.data.length ?? 0} files</Badge>
            </CardHeader>
            <CardBody className="space-y-1">
              {(evidence.data?.data ?? []).length === 0 ? (
                <EmptyState
                  kind="UNAVAILABLE"
                  title="No evidence bundle for this incident"
                  detail="Generate one from the engine (--evidence INC12345) or the Evidence page, then refresh."
                />
              ) : (
                (evidence.data?.data ?? []).map((file) => (
                  <div key={file.path} className="flex items-center justify-between gap-2">
                    <span className="mono truncate text-[11.5px]">{file.path}</span>
                    <span className="text-[11px] text-text-muted">{file.bytes} B</span>
                  </div>
                ))
              )}
              <Link to="/evidence" className="text-[11.5px] text-accent">
                Open evidence center →
              </Link>
            </CardBody>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Critical findings in scope</CardTitle>
            <Link to="/findings" className="text-[11.5px] text-accent">
              Findings center →
            </Link>
          </CardHeader>
          <CardBody className="space-y-1">
            {criticalFindings.length === 0 ? (
              <p className="text-[12px] text-text-muted">
                No critical or failed findings reported for the current context and namespace.
              </p>
            ) : (
              criticalFindings.slice(0, 8).map((finding) => (
                <div key={finding.id} className="flex items-start gap-2">
                  <StatusPill status={finding.severity} />
                  <span className="mono text-[11px] text-text-muted">{finding.resource || "—"}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-text">
                    {finding.finding}
                  </span>
                </div>
              ))
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pinned resources</CardTitle>
            <Badge tone="neutral">{pins.data?.data.length ?? 0}</Badge>
          </CardHeader>
          <CardBody className="space-y-1">
            {(pins.data?.data ?? []).length === 0 ? (
              <p className="text-[12px] text-text-muted">
                Pin resources from the inspector to keep the incident's key objects together.
              </p>
            ) : (
              (pins.data?.data ?? []).map((pin) => (
                <div key={pin.id} className="flex items-center justify-between gap-2">
                  <span className="mono truncate text-[11.5px]">{pin.id}</span>
                  <StatusPill status={pin.health} />
                </div>
              ))
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Export incident evidence</CardTitle>
          <Badge tone="neutral">structured values, never screenshots</Badge>
        </CardHeader>
        <CardBody className="flex flex-wrap gap-2">
          {(["findings", "events", "pods", "workloads"] as const).flatMap((domain) =>
            (["json", "csv", "ndjson"] as const).map((fmt) => (
              <Button key={`${domain}-${fmt}`} variant="outline" size="sm" asChild>
                <a href={exportUrl(domain, scope, fmt)} download>
                  {domain}.{fmt}
                </a>
              </Button>
            )),
          )}
        </CardBody>
      </Card>
    </div>
  );
}
