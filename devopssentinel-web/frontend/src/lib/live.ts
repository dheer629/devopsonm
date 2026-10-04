/** Helpers for the LIVE refresh loop and the opt-in live-data endpoints. */

/** NodePort endpoints the demo fixtures expose (`scripts/demo-resources.sh`). */
export const DEMO_DATABASE_PORT = "30432";
export const DEMO_KAFKA_PORT = "30092";
export const DEMO_DATABASE = { name: "demo", username: "demo", password: "demo-not-a-real-credential" };

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
 * the documented `127.0.0.1:30432` / `127.0.0.1:30092` demo endpoints time
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
