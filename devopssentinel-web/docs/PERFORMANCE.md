# Performance & Load Protection

## Design targets

| Target | Approach | Measured |
| --- | --- | --- |
| Shell visible < 1 s after frontend load | Single bundle, no blocking cluster call on boot | Build 840 kB JS / 43 kB CSS (261 kB / 8 kB gzip) |
| Route change near-instant | TanStack Query cache reused; no cluster call for cached keys | E2E navigation ~0.2–0.4 s including render |
| Cached table interaction < 100 ms | Virtualized rows; only the visible window is in the DOM | 5,000 rows → < 200 `tr` nodes (asserted in `DataTable.test.tsx`) |
| Search/filter < 100 ms | In-memory TanStack filtering over the loaded page of data | E2E filter assertions complete in ms |
| Back navigation performs no cluster query | Query cache + `staleTime` 15 s | `browser refresh keeps the current route` test |
| Graph interaction smooth | React Flow with `nodesDraggable={false}`, depth-bounded subgraph | Topology E2E < 300 ms |

## API load protection

| Mechanism | Value |
| --- | --- |
| TTL cache | 15 s, keyed by `operation|context|namespace|params` |
| Single-flight | Concurrent identical requests share one engine invocation |
| Cache eviction | LRU-ish by insert order, max 256 entries |
| Per-operation timeouts | 20–120 s per operation; hard cap 300 s |
| Output cap | 8 MB per stream (flagged `truncated` → `PARTIAL`) |
| Concurrency | Bounded by the operation timeout + single-flight; no fan-out from the UI |
| Live polling | Operator-controlled 0/5/10/30/60 s; **never below 5 s**; paused when the tab is hidden |
| Diagnostics | `/api/v1/diagnostics` exposes cache entries, hits, misses and the audit trail |

The UI never polls a cluster merely to decorate the page: every panel is driven by an explicit
operation, and cached data is labelled `CACHE • Ns old` rather than shown as live.

## Frontend virtualization evidence

`frontend/src/components/DataTable.test.tsx` renders a 5,000-row table and asserts fewer than 200
`tbody tr` elements exist in the DOM — i.e. rows are windowed, not all mounted.

## Reproducing

```bash
python -m pytest -q                     # includes timeout/cancellation tests
(cd frontend && npx vitest run)         # includes the 5,000-row virtualization test
(cd frontend && npx playwright test)    # route timing is visible per test
curl -s http://127.0.0.1:8765/api/v1/diagnostics | jq
```

## Known limits

* Parsing is linear over report lines; a very large report is bounded by the 8 MB output cap rather
  than streamed.
* The topology layout is a simple deterministic grid (column-major by index) — it is a readability
  aid, not a force-directed layout engine.
* There is no server-side pagination because the engine returns whole reports; the client virtualizes
  instead.
