/**
 * API-server address helpers.
 *
 * The discovered-endpoint list and the saved connection do not always spell the
 * same address the same way, so comparing them needs to normalise first.
 */

/**
 * Reduce an API server URL to `host:port` for comparison.
 *
 * A missing scheme is assumed to be `https` and a missing port `443`, matching
 * how a Kubernetes client would resolve the address.
 */
function endpointKey(value: string): string {
  if (!value) return "";
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return `${url.hostname.toLowerCase()}:${url.port || "443"}`;
  } catch {
    return value.toLowerCase().replace(/\/+$/, "");
  }
}

/**
 * Do two API server URLs point at the same host and port?
 *
 * Deliberately host:port rather than a string compare: the same endpoint is
 * written as `https://host.docker.internal:11259` in the discovery list and
 * sometimes as a bare `host.docker.internal:11259` in a saved override. A
 * literal compare would miss the endpoint the app is actually using and leave a
 * stale "Connect" button next to a live connection.
 */
export function sameEndpoint(a: string, b: string): boolean {
  const left = endpointKey(a);
  return Boolean(left) && left === endpointKey(b);
}
