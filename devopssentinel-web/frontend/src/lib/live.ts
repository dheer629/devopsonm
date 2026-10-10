/** Helpers for the LIVE refresh loop and the opt-in live-data endpoints. */

/**
 * NodePort endpoints the **optional E2E platform fixture** exposes
 * (`scripts/platform-resources.sh`). These are not properties of an arbitrary
 * cluster: a cluster that has no such NodePort has no such endpoint, and the
 * console must not present them as fact. `suggestSqlTarget` derives the real
 * starting point from what the cluster actually reports.
 */
export const PLATFORM_DATABASE_PORT = "30432";
export const PLATFORM_KAFKA_PORT = "30092";
export const PLATFORM_DATABASE = { name: "platform", username: "platform", password: "platform-not-a-real-credential" };

/**
 * Query keys a LIVE tick must not re-read.
 *
 * These are identity and scope metadata plus the two opt-in console probes:
 * none of them change on a seconds cadence, and `/system` resolves the node
 * address with its own kubectl call, so polling it every 5 s is pure waste.
 * Everything cluster-facing (pods, workloads, findings, events, topology,
 * metrics, …) is refreshed on every tick.
 */
const NON_LIVE_KEYS = new Set([
  "system",
  "contexts",
  "namespaces",
  "sql-console",
  "kafka-console",
  // Explicit, operator-driven reads: re-running them on a tick would spawn a
  // kubectl process every few seconds for no benefit.
  "logs",
  "log-view",
  "containers",
  "describe",
]);

/** True when a query key should be re-read on the LIVE interval. */
export function isLiveKey(queryKey: readonly unknown[]): boolean {
  const head = queryKey[0];
  return typeof head !== "string" || !NON_LIVE_KEYS.has(head);
}

/**
 * The host a live-data endpoint should default to.
 *
 * A NodePort answers on a *node* address, never on `127.0.0.1`: inside a
 * vcluster only the API port is published to the host, which is exactly why
 * the documented `127.0.0.1:30432` / `127.0.0.1:30092` platform endpoints time
 * out. The backend reports the first node InternalIP, so prefer it; fall back
 * to the host the page was served from, then to loopback.
 */
export function resolveLiveHost(
  nodeAddress: string | undefined | null,
  locationHost: string,
): string {
  const node = (nodeAddress ?? "").trim();
  if (node) return node;
  const host = (locationHost ?? "").trim();
  return host || "127.0.0.1";
}

/** A database Service as the engine reports it (only the fields we prefill from). */
export interface DiscoveredDatabase {
  name?: string;
  namespace?: string;
  type?: string;
  port?: string;
  cluster_ip?: string;
}

/** The starting point for the SQL console, and where it came from. */
export interface SqlTarget {
  host: string;
  port: string;
  /** `discovered` = a Service the cluster reported; `node` = a bare fallback;
   *  `fixture` = the optional E2E platform fixture. */
  source: "discovered" | "node" | "fixture";
  /** The discovered Service type, e.g. `ClusterIP`; empty when nothing was found. */
  serviceType: string;
  /**
   * True when the endpoint only answers from *inside* the cluster.
   *
   * The query runs server-side, and the container runs outside the cluster, so a
   * ClusterIP cannot be reached from here even though it is a real address. The
   * UI says so rather than letting the operator discover it as a timeout.
   */
  clusterOnly: boolean;
}

/**
 * Choose the SQL console's starting endpoint from what the cluster reports.
 *
 * Preferring the discovered Service keeps the console honest: the fields show an
 * address that exists in this cluster. The E2E platform fixture ports are only a
 * last resort and are never presented as a property of the cluster.
 */
export function suggestSqlTarget(
  discovered: DiscoveredDatabase | undefined,
  nodeAddress: string | undefined,
  locationHost: string,
): SqlTarget {
  const clusterIp = (discovered?.cluster_ip ?? "").trim();
  if (clusterIp) {
    const serviceType = (discovered?.type ?? "").trim();
    return {
      host: clusterIp,
      port: (discovered?.port ?? "").trim(),
      source: "discovered",
      serviceType,
      clusterOnly: serviceType !== "NodePort" && serviceType !== "LoadBalancer",
    };
  }
  return {
    host: resolveLiveHost(nodeAddress, locationHost),
    port: "",
    source: "node",
    serviceType: "",
    clusterOnly: false,
  };
}

/**
 * The optional E2E platform fixture's endpoint as a **complete** target.
 *
 * The fixture (`scripts/platform-resources.sh`) publishes its database on a
 * NodePort at the node address. The console used to fill in only the *port*, so
 * the fields showed the discovered ClusterIP paired with the fixture's NodePort
 * -- `10.102.76.185:30432` -- an address that exists nowhere, and one the
 * operator could not correct by reading the page. A target is always a host
 * *and* a port taken from the same source.
 */
export function fixtureSqlTarget(
  nodeAddress: string | undefined,
  locationHost: string,
): SqlTarget {
  return {
    host: resolveLiveHost(nodeAddress, locationHost),
    port: PLATFORM_DATABASE_PORT,
    source: "fixture",
    serviceType: "NodePort",
    clusterOnly: false,
  };
}
