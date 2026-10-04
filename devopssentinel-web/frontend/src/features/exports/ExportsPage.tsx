import { Download } from "lucide-react";

import { exportUrl } from "@/api/client";
import { PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { useApp } from "@/state/AppContext";

const DOMAINS: { id: string; title: string; detail: string }[] = [
  { id: "pods", title: "Pods", detail: "Name, phase, readiness, restarts, node, age" },
  { id: "workloads", title: "Workloads", detail: "Kind, ready replicas, status, resources" },
  { id: "findings", title: "Findings", detail: "Severity, domain, resource, evidence text" },
  { id: "events", title: "Events", detail: "Time, severity, reason, object, count, message" },
];

const FORMATS = ["json", "csv", "ndjson"] as const;

export function ExportsPage() {
  const { scope } = useApp();

  return (
    <div className="space-y-3">
      <PageHeader
        title="Exports"
        subtitle="Structured exports built from complete engine values — never a screenshot of a table."
        actions={
          <Badge tone="neutral">
            {scope.context || "—"} / {scope.namespace || "—"}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {DOMAINS.map((domain) => (
          <Card key={domain.id}>
            <CardHeader>
              <CardTitle>{domain.title}</CardTitle>
              <Badge tone="neutral">{domain.id}</Badge>
            </CardHeader>
            <CardBody className="space-y-2">
              <p className="text-[12px] text-text-muted">{domain.detail}</p>
              <div className="flex flex-wrap gap-2">
                {FORMATS.map((fmt) => (
                  <Button key={fmt} variant="outline" size="sm" asChild>
                    <a href={exportUrl(domain.id, scope, fmt)} download>
                      <Download className="h-3.5 w-3.5" /> {fmt.toUpperCase()}
                    </a>
                  </Button>
                ))}
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Export policy</CardTitle>
        </CardHeader>
        <CardBody className="space-y-1 text-[12px] text-text-muted">
          <p>
            Every export is generated server-side from the engine's collected values and passed through
            the same redaction used for API responses.
          </p>
          <p>
            Kubernetes Secret payloads, private keys, tokens and credentials are never included.
            Exports are written to your local downloads folder only — nothing is uploaded.
          </p>
          <p>
            Graph screenshots are intentionally not offered: they would lose precision and could omit
            evidence that the structured export retains.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
