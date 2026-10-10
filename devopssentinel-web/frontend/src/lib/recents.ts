/**
 * Local "recently viewed" trail (spec section 13).
 *
 * Stores only navigation coordinates the operator already sees on screen --
 * kind, name, namespace, route, and the scope they were viewed in. No resource
 * contents, no labels, no annotations, no Secret values, no credentials ever
 * reach localStorage (spec sections 174, 334). It is a convenience index, not a
 * cache, and it is deliberately capped and de-duplicated.
 */

export interface RecentEntry {
  kind: string;
  name: string;
  namespace: string;
  route: string;
  context: string;
  at: number;
}

const KEY = "dsweb.recents";
const MAX = 12;

function read(): RecentEntry[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (row): row is RecentEntry =>
        typeof row === "object" &&
        row !== null &&
        typeof (row as RecentEntry).name === "string" &&
        typeof (row as RecentEntry).route === "string",
    );
  } catch {
    return [];
  }
}

function write(entries: RecentEntry[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(entries.slice(0, MAX)));
  } catch {
    /* storage disabled -- harmless */
  }
}

export function readRecents(): RecentEntry[] {
  return read();
}

/** Record a visit. Re-visiting an entry moves it to the front. */
export function pushRecent(entry: Omit<RecentEntry, "at">): RecentEntry[] {
  const key = `${entry.kind}|${entry.namespace}|${entry.name}`;
  const rest = read().filter((row) => `${row.kind}|${row.namespace}|${row.name}` !== key);
  const next = [{ ...entry, at: Date.now() }, ...rest].slice(0, MAX);
  write(next);
  return next;
}

export function clearRecents(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* storage disabled -- harmless */
  }
}
