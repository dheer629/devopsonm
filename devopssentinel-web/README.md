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

### Linux / WSL (primary)

```bash
./devopssentinel-web            # binds 127.0.0.1:8765, serves the production build
./devopssentinel-web --open     # also opens Chrome
./devopssentinel-web --debug    # developer diagnostics panel
./devopssentinel-web --incident INC12345
```

### Windows

If the engine, `kubectl` and your kubeconfig live inside WSL (the usual setup), run the wrapper —
it starts the app inside WSL and WSL2 forwards `127.0.0.1`, so Chrome on Windows reaches it:

```bat
devopssentinel-web.cmd --open
set DSWEB_WSL_DISTRO=Ubuntu    rem override the distribution if needed
```

The wrapper normalises CRLF in the launcher, so a Windows checkout works without `dos2unix`.


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
| Incident workspace (`/incidents/:id`), PRE/POST baseline comparison (`/baselines`), Exports page (`/exports`) | ✅ |
| Doctor capability matrix, Settings, pins, history, local exports (JSON/CSV/NDJSON) | ✅ |
| Command palette (Ctrl+K, `/`), keyboard chords (`g d`, `g p`, …) | ✅ |
| 7 professional themes (5 dark / 2 light) + system auto, swatch picker, bubble surface language | ✅ |
| Virtualized tables (5,000-row inventory test), status = icon + text + colour | ✅ |
| SSE endpoints for live refresh and streamed logs | ✅ |
| pytest (48), Vitest (18), Playwright smoke + axe (frontend-only, fixture-backed) | ✅ |
| Live TLS inspection, interactive logs, DB/Kafka credential prompts | ⛔ CLI only (see parity matrix) |

See **[docs/FEATURE_PARITY_MATRIX.md](docs/FEATURE_PARITY_MATRIX.md)** for the complete
per-feature accounting — there is no silent feature loss.

## Interface & themes

A dense, calm operations surface with soft "bubble" geometry: pill navigation and controls, layered
elevation, blurred top bar and status bar, and rounded data surfaces. Seven themes ship built in,
switchable from the palette icon in the top bar (or **Settings → Theme**):

| Theme | Kind | Character |
| --- | --- | --- |
| **Midnight** | dark | default graphite operations theme |
| **Ocean** | dark | deep blue, high-contrast telemetry |
| **Nord** | dark | muted arctic palette |
| **Tokyo** | dark | night-city violet and cyan |
| **Graphite** | light | neutral light for bright rooms |
| **Daylight** | light | cool light with strong separation |
| **Solarized** | light | warm low-glare paper tone |

Plus **Follow system**, which resolves to Midnight/Graphite from the OS preference. The active theme
is written to `<html data-theme>` and persisted locally. Status is always **icon + text + colour**,
so nothing depends on the palette.

## Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Security

See **[docs/SECURITY.md](docs/SECURITY.md)** and the API contract in
**[docs/API.md](docs/API.md)**.

## Honest limitations

* Report rows are normalized from the engine's **plain-text report lines** (TAB-separated tables and
  `Kind/name [STATUS REASON]` blocks), not from a per-object JSON schema the engine does not yet
  emit. Rows that cannot be parsed confidently are never invented: the raw expert view always carries
  the original lines, argv and exit status.
* Workload rows are derived from pod owner references (`Deployment/x`, `StatefulSet/y`) because the
  engine's `--resources` report lists pods plus totals, not a separate workload table.
* `--self-test`, `--explain` and `--ui-debug` produce plain text in the engine, so they are exposed
  as raw text rather than typed rows.
* Interactive-only engine capabilities (live TLS probe, interactive log follow, credential prompts)
  are surfaced as explicit `UNAVAILABLE` responses with a documented reason instead of being
  re-implemented in Python.
* The Playwright suite runs against deterministic fixtures. Live-cluster validation was performed
  manually against a real vcluster — see [docs/VALIDATION.md](docs/VALIDATION.md) for the captured
  results and the defects it surfaced.

