import { CheckCircle2, Unplug } from "lucide-react";
import { useEffect, useState } from "react";

import { exportUrl } from "@/api/client";
import {
  useActivateConnection,
  useAutoDetectConnection,
  useConnections,
  useDeactivateConnection,
  useDiagnostics,
  useDiscoveredEndpoints,
  useHistory,
  useLiveSettings,
  usePairEndpoint,
  usePins,
  useProbeConnection,
  useRemovePin,
  useSystem,
  type ProbeResult,
} from "@/api/queries";
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
import { sameEndpoint } from "@/lib/endpoint";
import { THEMES } from "@/lib/themes";
import { useApp, type LiveInterval } from "@/state/AppContext";

export function SettingsPage() {
  const { theme, setTheme, live, setLive, scope, debug, resolvedTheme } = useApp();
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

      <ClusterConnectionCard />
      <DetectedClustersCard />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Appearance &amp; refresh</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <Row label="Theme">
              <Select value={theme} onValueChange={setTheme}>
                <SelectTrigger className="w-44" aria-label="Theme">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">Follow system</SelectItem>
                  {THEMES.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.label} · {item.kind}
                    </SelectItem>
                  ))}
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
            <Row label="Theme">
              <span className="mono">
                {resolvedTheme.label} ({resolvedTheme.kind})
              </span>
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

function DetectedClustersCard() {
  const discovery = useDiscoveredEndpoints();
  const pair = usePairEndpoint();
  const connections = useConnections();
  const disconnect = useDeactivateConnection();

  const data = discovery.data?.data;
  const endpoints = data?.endpoints ?? [];
  const containers = data?.containers ?? [];

  // Which endpoint is the live one? `serverOverride` is the address the app
  // actually uses, so it is the one to match against — the kubeconfig's own
  // `server` is often a host port-forward that a container cannot reach.
  const active = connections.data?.data.active ?? null;
  const health = connections.data?.data.health ?? null;
  const liveEndpoint = active?.serverOverride || active?.server || "";
  const connected = Boolean(health?.reachable);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Detected clusters</CardTitle>
        <span className="flex items-center gap-2">
          {connected ? (
            <Badge tone="ok">
              <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
              connected
            </Badge>
          ) : null}
          {data ? (
            <Badge tone={endpoints.length ? "ok" : "neutral"}>{endpoints.length} reachable</Badge>
          ) : null}
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-[12px] text-text-muted">
          A container cannot read the WSL filesystem, so a cluster is found by its published API port
          and proven with an unauthenticated <span className="mono">/version</span> call. Pairing then
          works out which kubeconfig opens that endpoint.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            disabled={discovery.isFetching}
            onClick={() => void discovery.refetch()}
          >
            {discovery.isFetching ? "Scanning…" : "Scan for clusters"}
          </Button>
          {data ? (
            <span className="text-[11px] text-text-muted">
              {data.probed} endpoint(s) probed · Docker socket{" "}
              {data.dockerAvailable ? "available" : "not mounted"}
            </span>
          ) : null}
        </div>

        {data && !data.dockerAvailable ? (
          <p className="text-[11.5px] text-warning">
            Mount <span className="mono">/var/run/docker.sock:/var/run/docker.sock:ro</span> to name
            the vcluster / kind / k3s container behind each endpoint and to pick up ports outside the
            common list.
          </p>
        ) : null}
        {data && data.dockerAvailable && !data.docker.usable ? (
          <p className="text-[11.5px] text-warning">
            The Docker socket is mounted but not readable by this process. Add{" "}
            <span className="mono">--group-add 0</span> (or the socket&apos;s group id,{" "}
            <span className="mono">stat -c %g /var/run/docker.sock</span>) so container-level
            discovery works. Detail: <span className="mono">{data.docker.error}</span>
          </p>
        ) : null}

        {containers.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Kubernetes containers on the Docker host
            </h4>
            {containers.map((item) => (
              <div key={item.name} className="flex items-center justify-between gap-2 text-[11.5px]">
                <span className="mono truncate">{item.name}</span>
                <span className="shrink-0 text-text-muted">
                  {item.kind} · {item.state} ·{" "}
                  {item.ports.length ? item.ports.join(", ") : "no published port"}
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {endpoints.length === 0 ? (
          <EmptyState
            title={discovery.isFetching ? "Scanning…" : "No reachable API server"}
            detail="Publish the cluster API on a host port — vcluster, kind and minikube do this by default — or type the endpoint into the API server override above."
          />
        ) : (
          <div className="space-y-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Reachable API servers
            </h4>
            {endpoints.map((endpoint) => {
              // A Docker-derived endpoint names the Kubernetes container that
              // publishes the port, so it provably belongs to a cluster we can
              // see. A sweep-only hit may be any API server on the host —
              // including one these credentials do not open, which answers
              // /version anonymously and then returns 401.
              const verified = Boolean(endpoint.kind);
              const connecting = pair.isPending && pair.variables === endpoint.server;
              // The endpoint the app is actually using. Only claim "connected"
              // when the backend also reports it reachable, so a stale override
              // cannot render a green button over a dead connection.
              const isLive = connected && sameEndpoint(endpoint.server, liveEndpoint);
              return (
                <div
                  key={endpoint.server}
                  className="flex items-center justify-between gap-2 border-b border-border pb-1"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="mono truncate text-[11.5px]">{endpoint.server}</span>
                      <Badge tone={verified ? "ok" : "warning"}>
                        {verified ? "verified" : "unverified"}
                      </Badge>
                      {isLive ? (
                        <Badge tone="ok">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          connected
                        </Badge>
                      ) : null}
                    </div>
                    <div className="truncate text-[10.5px] text-text-muted">
                      {endpoint.version || "version unknown"}
                      {endpoint.kind ? ` · ${endpoint.kind}` : ""}
                      {endpoint.container ? ` · ${endpoint.container}` : ""}
                      {` · ${endpoint.source}`}
                      {verified ? "" : " · no Kubernetes container found behind this port"}
                    </div>
                  </div>
                  {isLive ? (
                    // The same slot toggles: a connected endpoint offers
                    // Disconnect rather than a dead button, so the control that
                    // made the connection is the one that breaks it.
                    <Button
                      variant="success"
                      size="sm"
                      disabled={disconnect.isPending}
                      title={`Disconnect from ${active?.context ?? "this cluster"}`}
                      onClick={() => disconnect.mutate()}
                    >
                      <Unplug className="h-3.5 w-3.5" aria-hidden="true" />
                      {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
                    </Button>
                  ) : (
                    <Button
                      variant={verified ? "primary" : "default"}
                      size="sm"
                      disabled={pair.isPending}
                      onClick={() => pair.mutate(endpoint.server)}
                    >
                      {connecting ? "Connecting…" : "Connect"}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {pair.isSuccess && !pair.data.data.activated ? (
          <div className="space-y-1">
            <p className="text-[11.5px] text-critical">
              {pair.data.data.reason === "NO_KUBECONFIG"
                ? "No kubeconfig was found on the server, so there is nothing to authenticate with."
                : "That endpoint refused every kubeconfig on the server."}
            </p>
            {pair.data.data.advice ? (
              <p className="text-[11.5px] text-text-muted">{pair.data.data.advice}</p>
            ) : null}
            {pair.data.data.attempts.map((attempt) => (
              <p
                key={`${attempt.kubeconfig}:${attempt.context}`}
                className="mono text-[10.5px] text-text-muted"
              >
                {attempt.context} → {attempt.reason || "FAILED"}: {attempt.detail || "no detail"}
              </p>
            ))}
            {pair.data.data.reason === "NO_KUBECONFIG" ? (
              <p className="text-[11.5px] text-text-muted">
                Mount one with{" "}
                <span className="mono">-v &quot;$USERPROFILE/.kube:/host-kube:ro&quot;</span> and press
                Rescan.
              </p>
            ) : null}
          </div>
        ) : null}
        {pair.isSuccess && pair.data.data.activated ? (
          <p className="text-[11.5px] text-success">
            Connected to <span className="mono">{pair.data.data.activated.context}</span>
            {pair.data.data.activated.serverOverride
              ? ` via ${pair.data.data.activated.serverOverride}`
              : ""}
            .
          </p>
        ) : null}
        {pair.isError ? (
          <p className="text-[11.5px] text-critical">{String(pair.error)}</p>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ClusterConnectionCard() {
  const connections = useConnections();
  const activate = useActivateConnection();
  const autoDetect = useAutoDetectConnection();
  const deactivate = useDeactivateConnection();
  const probe = useProbeConnection();
  const live = useLiveSettings();

  const [override, setOverride] = useState("");
  const [insecure, setInsecure] = useState(false);
  const [namespace, setNamespace] = useState("");
  const [result, setResult] = useState<{ id: string; probe: ProbeResult } | null>(null);

  const data = connections.data?.data;
  const active = data?.active ?? null;
  const health = data?.health ?? null;
  const candidates = data?.candidates ?? [];

  const activeOverride = active?.serverOverride ?? "";
  const activeNamespace = active?.namespace ?? "";
  const activeInsecure = Boolean(active?.insecureSkipTlsVerify);
  const activeServer = active?.server ?? "";

  // Mirror the active connection into the form. An empty override is not a
  // no-op: it points the app at the server named inside the kubeconfig, which
  // for a vcluster is a host port-forward such as https://localhost:10093 that
  // a container can never reach. Keeping the form in step means Activate
  // cannot silently undo a working override.
  useEffect(() => {
    setOverride(activeOverride);
    setInsecure(activeInsecure);
    setNamespace(activeNamespace);
  }, [activeOverride, activeNamespace, activeInsecure]);

  // A server only the Docker host can reach. Saved connections like this look
  // configured and then fail on every page.
  const hostOnlyServer =
    Boolean(active) &&
    !activeOverride &&
    /^(?:https?:\/\/)?(?:localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(?::\d+)?\/?$/i.test(activeServer);

  const runProbe = (candidateId: string) =>
    probe.mutate(
      { candidateId, serverOverride: override, insecureSkipTlsVerify: insecure },
      { onSuccess: (envelope) => setResult({ id: candidateId, probe: envelope.data }) },
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cluster connection</CardTitle>
        {active ? (
          <Badge tone="ok">{active.environment}</Badge>
        ) : (
          <Badge tone="warning">not configured</Badge>
        )}
      </CardHeader>
      <CardBody className="space-y-3">
        {active ? (
          <div className="space-y-1 text-[12px]">
            <Row label="Context">
              <span className="mono">{active.context}</span>
            </Row>
            <Row label="Namespace">
              <span className="mono">{active.namespace || "—"}</span>
            </Row>
            <Row label="Kubeconfig">
              <span className="mono break-all">{active.effectiveKubeconfig}</span>
            </Row>
            {active.serverOverride ? (
              <Row label="API server override">
                <span className="mono">{active.serverOverride}</span>
              </Row>
            ) : null}
            {active.serverOverride && active.server ? (
              <Row label="Kubeconfig server">
                <span className="mono">{active.server}</span>
              </Row>
            ) : null}
          </div>
        ) : (
          <p className="text-[12px] text-text-muted">
            No cluster is connected, so every cluster page is empty. Activate a discovered
            kubeconfig below, or let auto-detect find the first reachable cluster.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            disabled={autoDetect.isPending}
            onClick={() => autoDetect.mutate({ force: true })}
          >
            {autoDetect.isPending ? "Detecting…" : "Auto-detect"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void connections.refetch()}>
            Rescan
          </Button>
          {active ? (
            <Button variant="ghost" size="sm" onClick={() => deactivate.mutate()}>
              Disconnect
            </Button>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-wide text-text-muted">
              API server override
            </span>
            <input
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]"
              placeholder={activeServer || "https://host.docker.internal:11259"}
              value={override}
              onChange={(event) => setOverride(event.target.value)}
            />
            <span className="text-[10.5px] text-text-muted">
              {override
                ? "The app will use this address instead of the kubeconfig's own server."
                : activeServer
                  ? `Empty — the kubeconfig's own server (${activeServer}) is used.`
                  : "Empty — the kubeconfig's own server is used."}
            </span>
          </label>
          <label className="space-y-1">
            <span className="text-[11px] uppercase tracking-wide text-text-muted">Namespace</span>
            <input
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]"
              placeholder="(context default)"
              value={namespace}
              onChange={(event) => setNamespace(event.target.value)}
            />
          </label>
        </div>
        <label className="flex items-start gap-2 text-[11.5px] text-text-muted">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={insecure}
            onChange={(event) => setInsecure(event.target.checked)}
          />
          Skip TLS verification for the API server — needed when a container reaches a cluster
          published on the Docker host, where the certificate name cannot match.
        </label>

        {hostOnlyServer ? (
          <p className="text-[11.5px] text-warning">
            This context points at <span className="mono">{activeServer}</span>, which inside a
            container is the container itself, not the Docker host — so every cluster page will be
            empty. Set the API server override to the cluster&apos;s published host port (for example{" "}
            <span className="mono">https://host.docker.internal:11259</span>) and press Activate, or
            press Connect on a detected cluster below.
          </p>
        ) : null}

        {candidates.length === 0 ? (
          <EmptyState
            title="No kubeconfig found on the server"
            detail="Mount one into the container (-v ~/.kube:/host-kube:ro) and press Rescan."
          />
        ) : (
          <div className="space-y-1">
            {candidates.map((candidate) => {
              const isActiveCandidate = Boolean(active) && active?.candidateId === candidate.id;
              return (
                <div
                  key={candidate.id}
                  className="flex items-center justify-between gap-2 border-b border-border pb-1"
                >
                  <div className="min-w-0">
                    <div className="mono flex items-center gap-2 truncate text-[11.5px]">
                      {candidate.context}
                      {isActiveCandidate ? (
                        <Badge tone={health?.reachable ? "ok" : "critical"}>
                          {health?.reachable ? "in use" : "unreachable"}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="truncate text-[10.5px] text-text-muted">
                      {candidate.environment} · {candidate.source} · {candidate.kubeconfig}
                    </div>
                    {result?.id === candidate.id ? (
                      <div
                        className={`text-[10.5px] ${
                          result.probe.reachable ? "text-success" : "text-critical"
                        }`}
                      >
                        {result.probe.reachable
                          ? `reachable · ${result.probe.serverVersion || "unknown"} · ${result.probe.namespaceCount} namespaces · ${result.probe.latencyMs}ms`
                          : `${result.probe.status}: ${result.probe.detail}`}
                      </div>
                    ) : null}
                  </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={probe.isPending}
                    onClick={() => runProbe(candidate.id)}
                  >
                    Test
                  </Button>
                  {isActiveCandidate ? (
                    // The context this app is already using. The same slot
                    // toggles: Disconnect while it answers, Reconnect when it
                    // does not — which is what a moved vcluster port looks like.
                    health?.reachable ? (
                      <Button
                        variant="success"
                        size="sm"
                        disabled={deactivate.isPending}
                        title={`Disconnect from ${candidate.context}${
                          active?.serverOverride ? ` (${active.serverOverride})` : ""
                        }`}
                        onClick={() => deactivate.mutate()}
                      >
                        <Unplug className="h-3.5 w-3.5" aria-hidden="true" />
                        {deactivate.isPending ? "Disconnecting…" : "Disconnect"}
                      </Button>
                    ) : (
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={autoDetect.isPending}
                        title={health?.detail || "The saved endpoint is not answering"}
                        onClick={() => autoDetect.mutate({ force: true })}
                      >
                        Reconnect
                      </Button>
                    )
                  ) : (
                    <Button
                      variant="default"
                      size="sm"
                      disabled={activate.isPending}
                      onClick={() =>
                        activate.mutate({
                          candidateId: candidate.id,
                          namespace,
                          serverOverride: override,
                          insecureSkipTlsVerify: insecure,
                        })
                      }
                    >
                      Activate
                    </Button>
                  )}
                </div>
                </div>
              );
            })}
          </div>
        )}

        {activate.isError ? (
          <p className="text-[11.5px] text-critical">{String(activate.error)}</p>
        ) : null}
        {(activate.data?.warnings ?? []).map((warning) => (
          <p key={warning} className="text-[11.5px] text-warning">
            {warning}
          </p>
        ))}
        {autoDetect.isError ? (
          <p className="text-[11.5px] text-critical">{String(autoDetect.error)}</p>
        ) : null}
        {autoDetect.isSuccess && !autoDetect.data.data.activated ? (
          <div className="space-y-1">
            <p className="text-[11.5px] text-warning">
              No reachable cluster found. {autoDetect.data.data.attempts.length} pairing
              attempt(s) were made
              {autoDetect.data.data.advice ? ` — ${autoDetect.data.data.advice}` : "."}
            </p>
            {autoDetect.data.data.attempts.slice(0, 4).map((attempt) => (
              <p
                key={`${attempt.context}-${attempt.server}`}
                className="mono text-[10.5px] text-text-muted"
              >
                {attempt.context} @ {attempt.server} → {attempt.reason}
                {attempt.detail ? `: ${attempt.detail}` : ""}
              </p>
            ))}
          </div>
        ) : null}
        {autoDetect.isSuccess && autoDetect.data.data.activated ? (
          <p className="text-[11.5px] text-success">
            Connected to{" "}
            <span className="mono">{autoDetect.data.data.activated.context}</span>
            {autoDetect.data.data.serverOverride ? (
              <>
                {" "}
                via <span className="mono">{autoDetect.data.data.serverOverride}</span>
              </>
            ) : null}
            {autoDetect.data.data.detected?.container ? (
              <>
                {" "}
                (detected through{" "}
                <span className="mono">{autoDetect.data.data.detected.container}</span>)
              </>
            ) : null}
            .
          </p>
        ) : null}

        <div className="border-t border-border pt-2">
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Live data — opt-in, read-only
          </h4>
          <label className="mt-1 flex items-center gap-2 text-[11.5px]">
            <input
              type="checkbox"
              checked={data?.live.sqlConsole ?? false}
              onChange={(event) => live.mutate({ sqlConsole: event.target.checked })}
            />
            Read-only SQL console
          </label>
          <label className="mt-1 flex items-center gap-2 text-[11.5px]">
            <input
              type="checkbox"
              checked={data?.live.kafkaTopics ?? false}
              onChange={(event) => live.mutate({ kafkaTopics: event.target.checked })}
            />
            Kafka topic listing
          </label>
          <p className="mt-1 text-[11px] text-text-muted">
            Each feature also needs a reachable database or broker. No credential is ever stored.
          </p>
        </div>
      </CardBody>
    </Card>
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
