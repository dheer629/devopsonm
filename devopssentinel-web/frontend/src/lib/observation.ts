/**
 * Chart observation.
 *
 * The Metrics API reports one *instantaneous* value per read (`kubectl top`),
 * so a usage chart has no history to draw unless something keeps sampling. That
 * sampling is a property of the page being open rather than of the LIVE switch:
 * the charts observe on their own, say so on the card, and can be paused.
 *
 * The cost is bounded and visible: two metrics endpoints, one read per interval,
 * only while a page that draws charts is mounted, and never while the tab is
 * hidden (TanStack Query pauses `refetchInterval` in a background tab).
 */
export const OBSERVE_INTERVAL_MS = 5_000;

/** The one-line state shown on a chart card next to its sample caption. */
export function observationNote(observing: boolean, intervalMs = OBSERVE_INTERVAL_MS): string {
  const seconds = Math.max(1, Math.round(intervalMs / 1000));
  return observing ? `observing every ${seconds}s` : "observation paused";
}
