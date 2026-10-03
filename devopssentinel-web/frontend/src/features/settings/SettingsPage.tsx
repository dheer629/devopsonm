import { exportUrl } from "@/api/client";
import { useDiagnostics, useHistory, usePins, useRemovePin, useSystem } from "@/api/queries";
import { EmptyState, Freshness, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { relative } from "@/lib/format";
import { useApp, type LiveInterval, type ThemeMode } from "@/state/AppContext";

export function SettingsPage() {
  const { theme, setTheme, live, setLive, scope, debug } = useApp();
  const system = useSystem();
  const pins = usePins();
  const history = useHistory();
  const removePin = useRemovePin();
  const diagnostics = useDiagnostics(debug);

  return (
    <div className="space-y-3">
      <PageHeader
        title="Settings"
        subtitle="Preferences are stored locally. No credentials or Secret values are ever persisted."
        actions={system.data ? <Freshness envelope={system.data} /> : null}
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Appearance &amp; refresh</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <Row label="Theme">
              <Select value={theme} onValueChange={(v) => setTheme(v as ThemeMode)}>
                <SelectTrigger className="w-40" aria-label="Theme">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Live refresh">
              <Select
                value={String(live)}
                onValueChange={(v) => setLive(Number(v) as LiveInterval)}
              >
                <SelectTrigger className="w-40" aria-label="Live refresh interval">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[0, 5, 10, 30, 60].map((option) => (
                    <SelectItem key={option} value={String(option)}>
                      {option === 0 ? "OFF" : `${option} sec`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
            <p className="text-[11.5px] text-text-muted">
              Polling never runs below five seconds and pauses while the tab is hidden.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Versions</CardTitle>
          </CardHeader>
          <CardBody className="space-y-1 text-[12px]">
            <Row label="DevOpsSentinel Web">
              <span className="mono">{system.data?.data.webVersion ?? "1.0.0"}</span>
            </Row>
            <Row label="Sentinel Engine">
              <span className="mono">4.2.2</span>
            </Row>
            <Row label="API Schema">
              <span className="mono">{system.data?.data.apiSchema ?? "1.0"}</span>
            </Row>
            <Row label="Mode">
              <Badge tone="ok">{system.data?.data.mode ?? "SUPERVISION [READ ONLY]"}</Badge>
            </Row>
            <Row label="Kubeconfig">
              <span className="mono truncate">{system.data?.data.kubeconfig ?? "—"}</span>
            </Row>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Exports</CardTitle>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-2">
            {(["pods", "workloads", "findings", "events"] as const).flatMap((domain) =>
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

        <Card>
          <CardHeader>
            <CardTitle>Pinned resources</CardTitle>
            <Badge tone="neutral">{pins.data?.data.length ?? 0}</Badge>
          </CardHeader>
          <CardBody className="space-y-1">
            {(pins.data?.data ?? []).length === 0 ? (
              <EmptyState
                title="No pinned resources"
                detail="Pin a resource from the inspector to keep it visible across sessions."
              />
            ) : (
              (pins.data?.data ?? []).map((pin) => (
                <div key={pin.id} className="flex items-center justify-between gap-2">
                  <span className="mono truncate text-[11.5px]">{pin.id}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removePin.mutate(pin.id)}
                    aria-label={`Unpin ${pin.id}`}
                  >
                    remove
                  </Button>
                </div>
              ))
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent resources</CardTitle>
            <Badge tone="neutral">{history.data?.data.length ?? 0}</Badge>
          </CardHeader>
          <CardBody className="space-y-1">
            {(history.data?.data ?? []).length === 0 ? (
              <EmptyState
                title="No history yet"
                detail="Resources you inspect are recorded locally to speed up navigation."
              />
            ) : (
              (history.data?.data ?? []).map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-2">
                  <span className="mono truncate text-[11.5px]">
                    {item.kind}/{item.name}
                  </span>
                  <span className="text-[11px] text-text-muted">{relative(item.visitedAt)}</span>
                </div>
              ))
            )}
          </CardBody>
        </Card>

        {debug ? (
          <Card>
            <CardHeader>
              <CardTitle>Developer diagnostics</CardTitle>
              <Badge tone="warning">debug</Badge>
            </CardHeader>
            <CardBody className="space-y-1 text-[11.5px]">
              <Row label="Cache entries">
                <span className="mono">{diagnostics.data?.data.cache.entries ?? 0}</span>
              </Row>
              <Row label="Cache hits / misses">
                <span className="mono">
                  {diagnostics.data?.data.cache.hits ?? 0} /{" "}
                  {diagnostics.data?.data.cache.misses ?? 0}
                </span>
              </Row>
              <Row label="Active route">
                <span className="mono">{window.location.pathname}</span>
              </Row>
              <Row label="Viewport">
                <span className="mono">
                  {window.innerWidth}×{window.innerHeight}
                </span>
              </Row>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[11.5px] text-text-muted">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}
