# API Contract (schema 1.0)

Base path: `/api/v1`. Every endpoint returns the same envelope.

## Envelope

```json
{
  "schemaVersion": "1.0",
  "toolVersion": "4.2.2",
  "timestamp": "2026-10-03T22:15:12+00:00",
  "context": "vcluster-docker_dev",
  "namespace": "default",
  "source": "LIVE",
  "status": "OK",
  "partial": false,
  "durationMs": 742,
  "cacheAgeMs": 0,
  "data": {},
  "warnings": [],
  "errors": []
}
```

| Field | Notes |
| --- | --- |
| `source` | `LIVE` \| `CACHE` \| `LOCAL` \| `PARTIAL` \| `UNAVAILABLE` |
| `status` | `OK` \| `INFO` \| `NOTICE` \| `WARNING` \| `CRITICAL` \| `FAILED` \| `UNKNOWN` \| `PARTIAL` |
| `partial` | true when the engine returned exit 4 or output was truncated |
| `cacheAgeMs` | non-zero only when `source == "CACHE"` |

Operation endpoints additionally return `raw`:

```json
{
  "envelope": { "...": "..." },
  "raw": {
    "engineArgv": ["bash", "DevOps_K8s_Sentinel_FINAL_GP.sh", "--no-color", "--resources", "--json"],
    "readOnlyCommand": "bash DevOps_K8s_Sentinel_FINAL_GP.sh --no-color --resources --json",
    "exitStatus": 0,
    "stdout": "{ ...engine JSON... }",
    "stderr": "",
    "durationMs": 742
  },
  "exitStatus": 0
}
```

## Endpoints

### System

| Method | Path | Data |
| --- | --- | --- |
| GET | `/system` | versions, mode, engine path, capabilities map, operation list |
| GET | `/version` | web version, API schema, mode |
| GET | `/capabilities` | `Capability[]` |
| GET | `/contexts` | `{ contexts: string[], current: string }` (read-only kubectl) |
| GET | `/namespaces?context=` | `{ namespaces: string[] }` (read-only kubectl) |
| GET | `/session` | local session info |
| GET | `/health` | engine health report (raw lines) |
| GET | `/doctor` | capability matrix (raw lines) |
| GET | `/diagnostics` | cache stats + audit trail (developer mode) |

### Cluster connections

The target cluster is a first-class, configurable object. Everything here is
read-only and local: the only side effect is the connection preference under the
private state directory. Payloads are **camelCase**, matching the browser types.

| Method | Path | Data |
| --- | --- | --- |
| GET | `/connections` | `{ files, candidates, active, health, kubectlAvailable, effectiveKubeconfig, stateDir, live }` |
| POST | `/connections/probe` | `ProbeResult` — reachability, server version, namespace count, latency, `reason` |
| POST | `/connections/activate` | the stored `ActiveConnection`; `warnings` explains a host-only server |
| POST | `/connections/deactivate` | `{ active: null }` |
| POST | `/connections/auto` | `{ activated, attempts, reason, advice, serverOverride, detected, serverVersion, health }` — detect **and** connect |
| POST | `/connections/import` | contexts from a pasted kubeconfig |
| GET | `/connections/discover` | reachable API servers on the Docker host + Kubernetes containers |
| POST | `/connections/pair` | `{ activated, attempts, reason, advice }` — pair an endpoint with its kubeconfig |
| GET | `/settings` | `{ connection, effectiveKubeconfig, live, kubectlAvailable, stateDir, files }` |
| POST | `/settings/live` | `{ sqlConsole, kafkaTopics }` — runtime toggles, no restart |

#### Automatic connection

A console that opens with no cluster looks broken, so the backend connects by
itself. Two things run:

1. **At startup** (`_autoconnect` in `main.py`, background task, off the request
   path). It probes the active connection first and does nothing when that works.
2. **On page load** (`POST /connections/auto` from the top bar), as a second
   line of defence for the case where the console came up before Docker or WSL
   was ready.

`/connections/auto` answers `ALREADY_CONNECTED` without probing when the current
connection is healthy, so it is safe to call on every load. Send
`{"force": true}` to reconnect regardless.

The Docker/WSL case is why `auto_connect` exists rather than a plain
kubeconfig probe. A vcluster kubeconfig names `https://localhost:<forward-port>`
because that is the port-forward `vcluster connect` opens on the workstation.
Inside a container `localhost` is the container itself, so that address can
never work. `auto_connect` therefore:

1. discovers host ports that actually answer `/version` (Docker socket
   inspection plus a port sweep),
2. re-probes each discovered endpoint using the kubeconfig's credentials with a
   `server_override`, skipping TLS verification because the certificate is issued
   for `localhost` rather than `host.docker.internal`,
3. activates the first pairing that authenticates, and
4. falls back to each kubeconfig's own server, which is already correct for
   Docker Desktop, a remote cluster or an in-cluster service account.

Every attempt is reported in `attempts[]` with its own `reason`, so a failure
names which credential/endpoint pair failed and why instead of saying only that
nothing worked. Set `DSWEB_AUTOCONNECT=0` to disable the startup pass.

`/connections` reports `health` separately from `active`, because a saved
connection can be *configured* and still be dead — a vcluster's published port
moves when the cluster restarts, so a pinned override goes stale. The UI uses
this to distinguish "connected" from "configured but unreachable" and to trigger
a reconnect.

| `health` field | Notes |
| --- | --- |
| `configured` | an `active` connection exists |
| `reachable` | it answered just now — the only field that means "connected" |
| `reason` | `UNAUTHORIZED`, `FORBIDDEN`, `TLS`, `UNREACHABLE`, `TIMEOUT`, `INVALID`, `FAILED` |
| `detail` | the kubectl message behind `reason` |
| `server` | the address actually used (`serverOverride` when set) |
| `serverVersion` | the API server version, when reachable |

`ActiveConnection` carries both servers, which is what makes the override
legible:

| Field | Notes |
| --- | --- |
| `server` | the API server named by the kubeconfig itself (often a host port-forward) |
| `serverOverride` | the address the app actually uses; empty means "use `server`" |
| `insecureSkipTlsVerify` | explicit opt-in; needed when the certificate name cannot match |
| `effectiveKubeconfig` | the materialised file every kubectl call and the engine are pinned to |

`ProbeResult.reason` is one of `UNAUTHORIZED`, `FORBIDDEN`, `TLS`,
`UNREACHABLE`, `TIMEOUT`, `INVALID`, `FAILED` (empty when reachable).
`POST /connections/pair` returns the same vocabulary at the top level plus
`advice`, because a port sweep finds *every* API server on the Docker host —
including ones that answer an unauthenticated `/version` and then reject the
client certificate with a 401. That is reported as `UNAUTHORIZED` ("this is not
your cluster"), never as a missing kubeconfig.

### Workloads

| Method | Path | Data |
| --- | --- | --- |
| GET | `/workloads` | `Workload[]` |
| GET | `/pods` | `Pod[]` |
| GET | `/pods/{name}` | engine triage report (text) |
| GET | `/pods/{name}/containers` | derived container list |
| GET | `/pods/{name}/events` | `Event[]` |
| GET | `/pods/{name}/logs?container=&previous=&tail=` | `LogBundle` (always `PARTIAL`) |
| GET | `/pods/{name}/dependencies` | `Graph` |
| GET | `/workloads/{kind}/{name}` | engine workload triage (text) |

### Inspect (read-only kubectl)

The engine exposes pod logs and a resource describe only in its interactive console, so these
views are backed by narrowly-scoped read-only `kubectl` calls. Every form is pinned in
`services/kube.py`; Secret payloads are never requested and all output is redacted.

| Method | Path | Data |
| --- | --- | --- |
| GET | `/logs?pod=&container=&tail=&since=&previous=&timestamps=` | `LogBundle` (`LIVE`) — one bounded `kubectl logs`; `since` ∈ `5m,15m,30m,1h,6h,24h` or empty |
| GET | `/containers?pod=` | `{ pod, containers: string[] }` — container picker for the log viewer |
| GET | `/describe?kind=&name=&format=` | `ResourceDescription` — `format` ∈ `describe, yaml, json, events`; `Secret` returns `403` |

### Graph

| Method | Path | Data |
| --- | --- | --- |
| GET | `/graph/{kind}/{name}` | `Graph` — every edge carries `evidence`, the engine report line it was read from |
| GET | `/graph/gitops` | `Graph` |
| GET | `/impact/{kind}/{name}` | `{ target, direct[], count, graph, confidence }` — reverse dependencies |
| GET | `/failure-path/{kind}/{name}` | `{ target, graph, unhealthy[], pathEdges[], note }` — only nodes the engine marked unhealthy |
| GET | `/path?kind=&name=` | alias of `/graph/...` |
| GET | `/pods/{name}/dependencies` | `Graph` — same engine operation as `/graph/Pod/{name}` |

`GraphEdge.evidence` is the engine's own statement, bounded to 300 characters. It
exists so a relationship can be explained rather than merely asserted; a
consumer that drops it is showing less than the engine reported (spec 37, 347).

`/failure-path` and `/impact` both derive from the same dependency report as
`/graph/...`, so all three agree on edges and confidence. `/failure-path` adds
the set of nodes the **engine** flagged and the edges attached to them; it never
infers a failure. `/impact` reverses the edges to answer "what references this?".

### GitOps

`/gitops`, `/gitops/sources`, `/gitops/kustomizations`, `/gitops/helmreleases`,
`/gitops/chain`, `/gitops/{kind}/{name}`, `/gitops/{kind}/{name}/timeline`.

`/gitops/{kind}/{name}` returns `{ object, graph }` — the inventory row plus the
chain it manages. `/gitops/{kind}/{name}/timeline` returns
`{ object, entries[], lagging, note }`. The engine reports a *current* and an
*applied* revision, not a history, so the timeline states exactly what was
observed and sets `lagging` when the two disagree; the note says transitions
before the observation are unavailable.

### PKI

| Method | Path | Data |
| --- | --- | --- |
| GET | `/certificates` | `Certificate[]` |
| GET | `/certificates/expiry` | `Certificate[]` from the engine's `--cert-expiry` audit |
| GET | `/certificates/duplicates` | `{ "<subject>": ["cert-a", "cert-b"] }` |
| GET | `/certificates/issuers` | `string[]` |
| GET | `/certificates/{name}` | `{ certificate, graph }` — adds a warning when the name is not in the inventory |
| GET | `/certificates/{name}/chain` | `{ certificate, chain[], depth, complete, terminated, note }` |
| GET | `/certificates/{name}/consumers` | `{ target, direct[], count, graph, confidence }` |
| GET | `/secrets` | Secret inventory + joined TLS certificate expiry; metadata only |
| POST | `/tls/inspect` | `UNAVAILABLE` by design |

The expiry route parses the audit table the engine emits
(`NAMESPACE/OBJECT/CN-SAN/ISSUER/EXPIRY/DAYS/STATUS`), reducing `Secret/x` to `x`
so the row is usable as an identifier by the other certificate routes. This is
the source of the console's expiry posture, so its buckets come from the engine's
own CRITICAL/WARNING/ATTENTION thresholds rather than a browser-side guess.

`/certificates/{name}/chain` walks the issuer names the inventory carries, with a
cycle guard. `terminated` records why the walk stopped — `root`, `cycle` or
`not-in-inventory` — and `complete` is true **only** for `root`. A chain that
stops because the issuer is absent is truncated, and the API says so instead of
implying a root.

### Network / Storage

| Method | Path | Data |
| --- | --- | --- |
| GET | `/network/services` | `ServiceResource[]` |
| GET | `/network/endpoints` | `ServiceResource[]` with ready / not-ready endpoint counts |
| GET | `/network/endpoint-gaps` | services with zero ready endpoints (`status=WARNING` when non-empty) |
| GET | `/network/port-path/{service}` | `{ service, graph }` — Ingress → Service → EndpointSlice → Pod |
| GET | `/network/policies/{pod}` | `{ target, direct[], count, graph, selectingPolicies[], isolated, note }` |
| GET | `/network/dns/{service}` | `{ service, fqdn, shortName, expectedAddress, readyEndpoints, resolves, note }` |
| GET | `/storage` | `PVCResource[]` |
| GET | `/storage/pvc/{name}` | `{ claim, graph }` |
| GET | `/storage/consumers/{name}` | `{ target, direct[], count, graph, confidence }` |
| GET | `/storage/mount-warnings` | `{ warnings[], unconsumed[], total }` |

`/network/policies/{pod}` reports which policies **select** the pod, not whether
traffic is permitted: `isolated` is true only when the engine reported a
selecting policy, and the note says the view is configuration only.

`/network/dns/{service}` does not query CoreDNS. It reports the Service record and
its observed endpoints, and answers `NOT PROBED` rather than claiming resolution
it did not verify.

`/storage/mount-warnings` splits claims the engine did not mark `OK` from claims
with no observed consumer. The two are different operational signals — an
unbound claim versus a provisioned volume nothing mounts — so they are reported
separately rather than merged into one list.

### Operations

`/findings`, `/triage`, `/events`, `/snapshot`, `/application-profile`, `/database`, `/kafka`, `/search?q=`,
`/pins` (GET/POST/DELETE), `/history` (GET/POST), `/notes/{incident_id}` (GET), `/notes` (POST),
`/baselines` (GET/POST), `/baselines/compare` (POST), `/evidence`, `/evidence/{id}`,
`/evidence/{id}/file?path=`, `/exports/{domain}?fmt=json|csv|ndjson|txt`.

`GET /events` prefers one bounded read-only `kubectl get events -o json` and
falls back to the engine's triage report. With no `namespace` it lists
cluster-wide (`--all-namespaces`) and prefixes each row's `object` with the
event's own namespace, e.g. `flux-system/Pod/web`. Without that, kubectl would
silently read only `default`, which is usually empty — and the page would look
broken rather than empty.

`GET /search?q=` covers **six domains in one query** — Pod, Service, Certificate,
GitOps, PVC and Finding — by running the same engine operations the domain pages
already call. No Kubernetes logic is re-implemented for search.

| Syntax | Effect |
| --- | --- |
| `transformer` | partial, case-insensitive match on name **and** namespace |
| `pod:redis` `svc:` `cert:` `gitops:` `pvc:` `finding:` | restrict to one kind (a bare prefix lists every resource of that kind) |
| `ns:payments` | restrict to a namespace |
| `status:failed` | restrict to a state |

`data` reports what actually happened, so a partial result is never silent:

```json
{
  "query": "pod:redis", "terms": ["redis"], "filters": { "kind": "Pod" },
  "results": [
    { "kind": "Pod", "name": "redis-5d66f5d4b6-ct9xs", "namespace": "learnalgorithm",
      "route": "/workloads/pods/redis-5d66f5d4b6-ct9xs", "state": "OK",
      "source": "LIVE", "engine": "workloads.resources" }
  ],
  "total": 4, "searched": ["Pod"], "unavailable": []
}
```

Each hit carries its engine operation as source attribution, and `unavailable`
names any domain that could not be read.

### Streaming (SSE)

`GET /api/v1/stream/live` and `GET /api/v1/stream/logs?name=` emit `open`, `heartbeat`/`log`,
`result`, `error`, `close` events.

## Errors

| Code | Meaning |
| --- | --- |
| 400 | invalid context/namespace/name (validation) |
| 403 | origin not allowed (the body lists the origins that are trusted, including the one the app is served on), evidence path escapes the evidence root, or a Secret describe |
| 404 | unknown export domain or missing evidence file |
| 413 | request body too large |

Engine failures are **not** HTTP errors: they are reported inside the envelope
(`status`, `errors[]`, `warnings[]`) so the UI can explain reason, impact and the next safe action
without leaking a stack trace.
