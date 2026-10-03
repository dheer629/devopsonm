import { useMemo } from "react";

import { useDoctor, useSystem } from "@/api/queries";
import { ErrorState, Freshness, LoadingRows, PageHeader, RawView } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { useApp } from "@/state/AppContext";

interface Row {
  name: string;
  status: string;
  version: string;
}

export function DoctorPage() {
  const { scope } = useApp();
  const doctor = useDoctor(scope);
  const system = useSystem();

  const rows = useMemo<Row[]>(() => {
    const lines = (doctor.data?.envelope.data ?? "").split("\n");
    const parsed: Row[] = [];
    for (const line of lines) {
      const cells = line.trim().split(/\s{2,}|\t/).filter(Boolean);
      if (cells.length < 2) continue;
      const [name, status, version = ""] = cells;
      if (!name || !status) continue;
      parsed.push({ name, status, version });
    }
    return parsed;
  }, [doctor.data]);

  const available = rows.filter((row) => row.status.includes("AVAILABLE") && !row.status.includes("UNAVAILABLE"));
  const unavailable = rows.filter((row) => row.status.includes("UNAVAILABLE"));

  return (
    <div className="space-y-3">
      <PageHeader
        title="Doctor"
        subtitle="Capability matrix — a missing optional capability disables only that feature."
        actions={doctor.data ? <Freshness envelope={doctor.data.envelope} /> : null}
      />

      <Card>
        <CardHeader>
          <CardTitle>Local toolchain</CardTitle>
          <Badge tone="neutral">
            engine {system.data?.data.engineAvailable ? "present" : "missing"} · bash{" "}
            {system.data?.data.bashAvailable ? "present" : "missing"}
          </Badge>
        </CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {Object.entries(system.data?.data.capabilities ?? {}).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1">
              <span className="mono text-[11.5px] text-text">{key}</span>
              <Badge tone={value ? "ok" : "unknown"}>{value ? "AVAILABLE" : "UNAVAILABLE"}</Badge>
            </div>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Engine capability report</CardTitle>
          <Badge tone={unavailable.length ? "warning" : "ok"}>
            {available.length} available · {unavailable.length} unavailable
          </Badge>
        </CardHeader>
        <CardBody className="p-0">
          {doctor.isLoading ? <LoadingRows /> : null}
          {doctor.data?.envelope.errors.length ? (
            <div className="p-3">
              <ErrorState envelope={doctor.data.envelope} onRetry={() => void doctor.refetch()} />
            </div>
          ) : null}
          {rows.length > 0 ? (
            <table className="w-full text-[12px]">
              <thead className="bg-panel-2">
                <tr>
                  <th className="px-3 py-1.5 text-left text-[11px] uppercase tracking-wide text-text-muted">
                    Capability
                  </th>
                  <th className="px-3 py-1.5 text-left text-[11px] uppercase tracking-wide text-text-muted">
                    Status
                  </th>
                  <th className="px-3 py-1.5 text-left text-[11px] uppercase tracking-wide text-text-muted">
                    Version
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.name} className="border-b border-border/50">
                    <td className="mono px-3 py-1">{row.name}</td>
                    <td className="px-3 py-1">
                      <Badge
                        tone={
                          row.status.includes("UNAVAILABLE")
                            ? "unknown"
                            : row.status.includes("OPTIONAL")
                              ? "info"
                              : "ok"
                        }
                      >
                        {row.status}
                      </Badge>
                    </td>
                    <td className="mono px-3 py-1 text-text-muted">{row.version || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </CardBody>
      </Card>

      <RawView raw={doctor.data?.raw} />
    </div>
  );
}
