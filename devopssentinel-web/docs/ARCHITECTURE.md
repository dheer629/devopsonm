# Architecture

## Principle

**One operational engine.** The Bash utility (`DevOps_K8s_Sentinel_FINAL_GP.sh`) owns every piece of
Kubernetes, Flux, Helm, PKI and platform intelligence. DevOpsSentinel Web is a *presentation and
correlation layer* on top of it. No Kubernetes algorithm exists twice.

```
┌──────────┐   typed HTTP / SSE    ┌──────────────┐   argv (allowlisted)   ┌─────────────────────────┐
│  Chrome  │ ────────────────────► │   FastAPI    │ ─────────────────────► │ DevOpsSentinel adapter  │
│ React UI │ ◄──────────────────── │  (backend)   │ ◄───────────────────── │  --json machine mode    │
└──────────┘   envelope + raw      └──────────────┘   engine JSON object   └───────────┬─────────────┘
                                                                                        │
                                                                          kubectl / Flux / Helm / cluster
```

## Backend layers

| Module | Responsibility |
| --- | --- |
| `app/config.py` | Settings, versions, paths, bounds, origin allowlist |
| `app/security.py` | Redaction, name/context/kind validation, read-only verb guard, origin check |
| `app/services/runner.py` | `asyncio` subprocess execution: argv arrays only, timeout + cancellation, output cap, audit trail |
| `app/services/sentinel.py` | The **only** module that knows engine argv. Operation registry → argv, `--json` parse |
| `app/services/parsers.py` | Plain report lines → typed rows (pods, workloads, certs, GitOps, services, PVCs, findings, capabilities, events, graphs, logs) |
| `app/services/cache.py` | 15 s TTL cache with single-flight de-duplication |
| `app/services/kube.py` | Two narrowly-scoped **read-only** kubectl discovery calls (contexts, namespaces) |
| `app/services/sessions.py` | Local operator state: pins, history, notes, baselines (`~/.devopssentinel-web`) |
| `app/services/evidence.py` | Evidence bundle listing/preview + local export formatting |
| `app/services/streaming.py` | SSE event framing and long-operation progress |
| `app/api/*` | Versioned routers (`/api/v1/...`) returning the standard envelope |

### Request flow

1. UI requests `GET /api/v1/pods?context=X&namespace=Y`.
2. `api/deps.scope` validates context and namespace (DNS-1123 / context regex).
3. `deps.invoke` checks the TTL cache keyed by `operation|context|namespace|params`.
4. On miss, `SentinelAdapter` builds `["bash", engine, "--no-color", "--context", X, "--namespace", Y,
   "--resources", "--json"]`, passes it through `assert_read_only`, and runs it.
5. `Runner` bounds the call, redacts stdout/stderr, records an audit entry.
6. The engine's JSON object is parsed, the normalizer turns `lines` into typed rows, and a standard
   envelope is returned with `source`, `status`, `partial`, `durationMs`, `cacheAgeMs`, plus the
   raw evidence (engine argv, exit status, stdout) for the expert view.

### Exit-code mapping

| Engine exit | Envelope status | Meaning |
| --- | --- | --- |
| 0 | `OK` | successful collection, no failing findings |
| 1 | `WARNING` | collection succeeded, failing findings exist |
| 2 | `FAILED` | invalid input/configuration |
| 3 | `FAILED` | bootstrap API/authentication failure |
| 4 | `PARTIAL` | required data unavailable |
| 124 | `FAILED` | adapter timeout (child terminated) |
| 127 | `UNAVAILABLE` | engine or bash missing |

## Frontend layers

* **`state/AppContext.tsx`** — theme, scope (context/namespace), live interval, panel sizes,
  current selection. Only harmless preferences are persisted to `localStorage`.
* **`api/client.ts` / `api/queries.ts`** — fetch wrapper and TanStack Query hooks. Query keys always
  embed `context` and `namespace`, so switching scope invalidates exactly the affected features.
* **`components/AppShell.tsx`** — top bar, collapsible nav, resizable inspector, status bar,
  command palette, global keyboard chords.
* **`components/DataTable.tsx`** — TanStack Table + TanStack Virtual. Only the visible window is in
  the DOM, which keeps 5,000-row inventories responsive.
* **`features/*`** — one folder per operational domain. Each page is small and reads from typed
  hooks; no page contains engine knowledge.
* **`lib/status.ts`** — the single status/confidence vocabulary. Every status renders as
  **icon + text + colour**.

## Data contract

Every endpoint returns the envelope from `docs/API.md`. The UI never reverse-engineers command
output: it either consumes typed rows or shows the raw expert view verbatim.

## Read-only guarantee

Three independent layers:

1. **Registry** — the browser can only name an operation id that exists in `OPERATIONS`.
2. **Guard** — `assert_read_only()` rejects any argv containing a mutation verb
   (`apply`, `delete`, `patch`, `scale`, `rollout`, `reconcile`, `suspend`, `upgrade`, …).
3. **Adapter scope** — kubectl is invoked only for `config get-contexts`, `config current-context`
   and `get namespaces`.

There is no `/exec`, `/shell` or arbitrary-command endpoint; a test asserts those routes 404.

## Streaming

SSE (`text/event-stream`) is used for live refresh progress and streamed logs. WebSockets are
deliberately not used — SSE is sufficient and simpler to bound.
