# DevOpsSentinel Web

A local, read-only **Kubernetes / GitOps / PKI / ETDP operations control center** that runs in
Chrome and is backed by the existing DevOpsSentinel Bash engine.

```
Chrome  →  React UI  →  typed HTTP/SSE API  →  FastAPI  →  DevOpsSentinel adapter
                                                              ↓
                                            DevOps_K8s_Sentinel_FINAL_GP.sh
                                                              ↓
                                                   kubectl / Flux / Helm / Kubernetes
```

The Bash utility remains the **single operational engine**. The browser never executes a shell
command: it requests an allowlisted *operation id* with validated scope, and the backend maps that
to an engine invocation in `--json` mode. There is no ANSI scraping, no duplicated Kubernetes
intelligence and **no Kubernetes mutation of any kind**.

## Quick start

```bash
./devopssentinel-web            # binds 127.0.0.1:8765, serves the production build
./devopssentinel-web --open     # also opens Chrome
./devopssentinel-web --debug    # developer diagnostics panel
./devopssentinel-web --incident INC12345
```

Startup output:

```
DevOpsSentinel Web v1.0.0

Sentinel     v4.2.2        READY
Backend                    READY
Frontend                   READY
Kubernetes                 CONNECTED
Context                    pny9-11-ccd3-oidc
Namespace                  pny9-etdp-ecev-1131
Mode                       SUPERVISION [READ ONLY]

Open:
http://127.0.0.1:8765
```

Requirements: Python 3.11+, Bash 4.4+, `kubectl`, `jq`, and an engine checkout one directory above
`devopssentinel-web/` (or next to the launcher). No Docker, no sudo, no `/usr/local`, no cluster
deployment.

## Build

```bash
./scripts/build.sh              # install, typecheck, test, build, package
./scripts/build.sh --skip-tests # faster local iteration
./scripts/test.sh               # pytest + vitest + Playwright + axe
```

## What is implemented

| Area | Status |
| --- | --- |
| One-command launcher, 127.0.0.1 default, browser open (WSL-aware) | ✅ |
| FastAPI adapter, allowlisted operations, read-only guard | ✅ |
| Standard response envelope (schemaVersion, source, status, partial, durationMs, cacheAgeMs) | ✅ |
| Short-TTL cache with single-flight de-duplication + audit trail | ✅ |
| Central redaction (tokens, JWTs, bearer, URL creds, private keys, k=v secrets) | ✅ |
| Origin allowlist, security headers, CSP, request-size and read-only guards | ✅ |
| Dashboard (problem-first), Findings center, Workloads + Pods, Pod detail, Logs, Events | ✅ |
| Topology graph (React Flow), impact/reverse dependencies, failure-path filter | ✅ |
| GitOps command center (sources → Kustomization → HelmRelease chain) | ✅ |
| PKI / TLS dashboard, expiry posture, consumer/reference tracing | ✅ |
| Network services + endpoint gaps, Storage PVC center | ✅ |
| ETDP / Database / Kafka / Smart Health report views | ✅ |
| Doctor capability matrix, Settings, pins, history, local exports (JSON/CSV/NDJSON) | ✅ |
| Command palette (Ctrl+K, `/`), keyboard chords (`g d`, `g p`, …), theme dark/light/system | ✅ |
| Virtualized tables (5,000-row inventory test), status = icon + text + colour | ✅ |
| SSE endpoints for live refresh and streamed logs | ✅ |
| pytest (48), Vitest (18), Playwright smoke + axe (frontend-only, fixture-backed) | ✅ |
| Live TLS inspection, interactive logs, DB/Kafka credential prompts | ⛔ CLI only (see parity matrix) |

See **[docs/FEATURE_PARITY_MATRIX.md](docs/FEATURE_PARITY_MATRIX.md)** for the complete
per-feature accounting — there is no silent feature loss.

## Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Security

See **[docs/SECURITY.md](docs/SECURITY.md)** and the API contract in
**[docs/API.md](docs/API.md)**.

## Honest limitations

* Report rows are normalized from the engine's **plain-text report lines**, not from a per-object
  JSON schema the engine does not yet emit. Rows that cannot be parsed confidently are never
  invented: the raw expert view always carries the original lines.
* `--self-test`, `--explain` and `--ui-debug` produce plain text in the engine, so they are exposed
  as raw text rather than typed rows.
* Interactive-only engine capabilities (live TLS probe, interactive log follow, credential prompts)
  are surfaced as explicit `UNAVAILABLE` responses with a documented reason instead of being
  re-implemented in Python.
* The Playwright suite runs against deterministic fixtures. Real-cluster validation is performed by
  the existing DevOpsSentinel WSL E2E harness (`devopssentinel-e2e/`).
