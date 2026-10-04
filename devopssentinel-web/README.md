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

## Demo fixtures (optional)

Every domain page is driven by real cluster objects. If a namespace is empty, the corresponding page
legitimately reports nothing. To exercise **all** pages end to end, deploy the bundled fixtures:

```bash
scripts/demo-resources.sh up   default     # default namespace is `default`
scripts/demo-resources.sh down default     # one-command cleanup
scripts/demo-resources.sh pvc  <namespace> <name> [size]   # standalone PVC
```

This creates a labelled (`devopssentinel.io/demo=true`) set of *real* objects, using only images
already present in the cluster:

| Page | Fixture |
| --- | --- |
| Workloads / Pods / Events / Topology | `Deployment/demo-web` (podinfo) + `Deployment/demo-postgres` |
| Storage | `demo-data` (1Gi) and `demo-cache` (512Mi) bound by `demo-web`, plus `demo-postgres-data` (2Gi) and `demo-kafka-data` (2Gi) — every PVC reports its consuming pod |
| Network | `Service/demo-web`, `Service/postgres`, `Service/kafka` with live endpoints, plus NodePorts `30432` (PostgreSQL) and `30092` (Kafka) |
| Database | `Service/postgres` → ready endpoint from `--postgres-discovery`, and a **real seeded schema**: `demo_customers` (10), `demo_orders` (60), `demo_events` (60) and the view `v_customer_value` |
| Kafka | a real single-node **Kafka 3.9.1 (KRaft)** broker with topics `orders`, `payments`, `events` (3 partitions each), 25 records per topic and the `demo-reader` consumer group with committed offsets |
| PKI / TLS | `Secret/demo-tls` (locally generated, 365 days) plus a cert-manager-issued `demo-certman-tls` when cert-manager is installed |

PostgreSQL and Kafka both write to PersistentVolumes, so the seeded schema, topics
and offsets survive a pod or cluster restart. Re-seed at any time with:

```bash
scripts/seed-demo-data.sh default     # drops and recreates the demo schema
```

## Optional client tools (`psql`, Kafka CLI)

The Doctor page reports `psql`, `kafka-topics.sh`, `kafka-topics`,
`kafka-consumer-groups.sh` and `kafka-consumer-groups` when they are missing. They are only
needed for the engine's *interactive* checks and for hands-on verification — the app itself
never requires them. Install them into `~/.local` **without sudo**:

```bash
scripts/install-cli-tools.sh              # both
scripts/install-cli-tools.sh --psql-only  # PostgreSQL client only
```

It unpacks the distro's PostgreSQL client `.deb` files (no root needed), downloads a Temurin JDK
and the Apache Kafka CLI, and writes thin wrappers into `~/.local/bin` — which is on `PATH` on
most distros. Restart the backend afterwards so the engine picks them up.

`pvc <namespace> <name>` creates a standalone PVC anywhere. The `local-path` provisioner binds on
first consumer, so a PVC with no consuming pod stays `Pending` — which the Storage page reports as
`WARNING` rather than hiding it.

The read-only adapter is unaffected: the script performs the explicitly scoped setup, exactly like the
`devopssentinel-e2e/` harness.

## Opt-in live data (read-only SQL console + Kafka topics)

Both are **off by default**. The browser stays a pure read-only supervision surface unless you
explicitly enable them:

```bash
./devopssentinel-web --enable-sql-console --enable-kafka-topics
# or, equivalently, with environment variables:
DSWEB_ENABLE_SQL_CONSOLE=1 DSWEB_ENABLE_KAFKA_TOPICS=1 ./devopssentinel-web
```

| Where | What it does |
| --- | --- |
| `/database` → **SQL** tab | Runs ONE read-only statement against a host/port/database/username/password you type in. Credentials live in one request body only — never stored, logged, exported or audited. Only `SELECT`/`WITH`/`SHOW`/`EXPLAIN`/`TABLE`/`VALUES`/`\d` is accepted, chained statements are rejected, and the session is forced read-only **on the server** (`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`) so it cannot mutate data. |
| `/kafka` → **Topics** tab | Sends ONE read-only Kafka `Metadata` (API key 3, version 1) request and lists topic names, partition counts and brokers. No credentials, no consumer groups, no offsets, no writes. |

The demo fixtures are exposed for exactly this: **PostgreSQL at `<node-ip>:30432`** (database/user
`demo`) and **Kafka at `<node-ip>:30092`** with the topics `orders`, `payments` and `events`
(3 partitions each). The full contract — including what the allowlist does *not* protect against —
is in [`docs/SECURITY.md` §2a](docs/SECURITY.md).

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
| Network services + endpoint gaps, Storage PVC centre (namespace, capacity, StorageClass, consuming pod) | ✅ |
| Database page: Services table, Data view (backing pods + PVCs), Report/Raw + availability panel | ✅ |
| Database page: **SQL** tab — opt-in read-only console with allowlist + server-forced read-only session | ✅ |
| Kafka page: Brokers table with bootstrap candidates, **Topics** tab (live listing + availability), Data view, Report/Raw | ✅ |
| Kafka page: **Topics** tab — opt-in live topic/partition listing via one Metadata request | ✅ |
| ETDP / Smart Health report views | ✅ |
| Incident workspace (`/incidents/:id`), PRE/POST baseline comparison (`/baselines`), Exports page (`/exports`) | ✅ |
| Doctor capability matrix, Settings, pins, history, local exports (JSON/CSV/NDJSON) | ✅ |
| Command palette (Ctrl+K, `/`), keyboard chords (`g d`, `g p`, …) | ✅ |
| 7 professional themes (5 dark / 2 light) + system auto, swatch picker, bubble surface language | ✅ |
| Virtualized tables (5,000-row inventory test), status = icon + text + colour | ✅ |
| SSE endpoints for live refresh and streamed logs | ✅ |
| pytest (114), Vitest (18), Playwright smoke + axe (frontend-only, fixture-backed) | ✅ |
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

