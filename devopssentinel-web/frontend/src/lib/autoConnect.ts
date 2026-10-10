/**
 * Remember an explicit "disconnect" so auto-connect respects it.
 *
 * The console connects to a cluster by itself on load. Without this, pressing
 * Disconnect and then reloading would silently reconnect, which makes the
 * button look broken. An explicit disconnect is an instruction, so it wins over
 * automation until the operator asks for a connection again.
 */

const KEY = "dsweb.autoConnectSuppressed";

export function isAutoConnectSuppressed(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setAutoConnectSuppressed(suppressed: boolean): void {
  try {
    if (suppressed) {
      window.localStorage.setItem(KEY, "1");
    } else {
      window.localStorage.removeItem(KEY);
    }
  } catch {
    /* storage disabled -- auto-connect simply keeps its default behaviour */
  }
}
