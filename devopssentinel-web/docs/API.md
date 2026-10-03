# API Contract (schema 1.0)

Base path: `/api/v1`. Every endpoint returns the same envelope.

## Envelope

```json
{
  "schemaVersion": "1.0",
  "toolVersion": "4.2.2",
  "timestamp": "2026-10-03T22:15:12+00:00",
  "context": "pny9-11-ccd3-oidc",
  "namespace": "pny9-etdp-ecev-1131",
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

### Graph

| Method | Path | Data |
| --- | --- | --- |
| GET | `/graph/{kind}/{name}` | `Graph` |
| GET | `/graph/gitops` | `Graph` |
| GET | `/impact/{kind}/{name}` | `{ target, direct[], graph, confidence }` |
| GET | `/failure-path/{kind}/{name}` | `{ graph, unhealthy[], pathEdges[], note }` |
| GET | `/path?kind=&name=` | alias of `/graph/...` |

### GitOps

`/gitops`, `/gitops/sources`, `/gitops/kustomizations`, `/gitops/helmreleases`,
`/gitops/chain`, `/gitops/{kind}/{name}`, `/gitops/{kind}/{name}/timeline`.

### PKI

`/certificates`, `/certificates/expiry`, `/certificates/duplicates`, `/certificates/issuers`,
`/certificates/{name}`, `/certificates/{name}/chain`, `/certificates/{name}/consumers`,
`POST /tls/inspect` (returns `UNAVAILABLE` by design).

### Network / Storage

`/network/services`, `/network/endpoints`, `/network/endpoint-gaps`,
`/network/port-path/{service}`, `/network/policies/{pod}`, `/network/dns/{service}`,
`/storage`, `/storage/pvc/{name}`, `/storage/consumers/{name}`, `/storage/mount-warnings`.

### Operations

`/findings`, `/triage`, `/events`, `/snapshot`, `/etdp`, `/database`, `/kafka`, `/search?q=`,
`/pins` (GET/POST/DELETE), `/history` (GET/POST), `/notes/{incident_id}` (GET), `/notes` (POST),
`/baselines` (GET/POST), `/baselines/compare` (POST), `/evidence`, `/evidence/{id}`,
`/evidence/{id}/file?path=`, `/exports/{domain}?fmt=json|csv|ndjson|txt`.

### Streaming (SSE)

`GET /api/v1/stream/live` and `GET /api/v1/stream/logs?name=` emit `open`, `heartbeat`/`log`,
`result`, `error`, `close` events.

## Errors

| Code | Meaning |
| --- | --- |
| 400 | invalid context/namespace/name (validation) |
| 403 | origin not allowed, or evidence path escapes the evidence root |
| 404 | unknown export domain or missing evidence file |
| 413 | request body too large |

Engine failures are **not** HTTP errors: they are reported inside the envelope
(`status`, `errors[]`, `warnings[]`) so the UI can explain reason, impact and the next safe action
without leaking a stack trace.
