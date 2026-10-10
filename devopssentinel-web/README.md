# DevOpsSentinel Web

A local, read-only **Kubernetes / GitOps / PKI / application profile operations control center** that runs in
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

### Docker Desktop

A container image is provided for Docker Desktop / Compose. Build from the repository root,
because the backend resolves the Bash engine one directory above the web project:

```bash
docker build -f devopssentinel-web/Dockerfile -t devopssentinel-web:1.0.0 .
docker run -d --name devopssentinel-web --restart unless-stopped -p 127.0.0.1:8765:8765 devopssentinel-web:1.0.0
```

or with Compose:

```bash
docker compose -f devopssentinel-web/docker-compose.yml up -d --build
```

Then open <http://127.0.0.1:8765>. The image runs as UID 10001, ships `kubectl` v1.31.4
(checksum-verified at build time) plus `bash`/`jq`/`openssl`/`curl`, and embeds the engine at
`/app/DevOps_K8s_Sentinel_FINAL_GP.sh`. It serves the prebuilt `frontend/dist`, so run
`./scripts/build.sh` first if that directory is missing.

Without a kubeconfig the UI still loads; the cluster pages report the scope as unavailable rather
than failing. Mount one read-only to make them live:

```bash
docker run -d --name devopssentinel-web -p 127.0.0.1:8765:8765 \
  -v "$USERPROFILE/.kube/config:/home/dsweb/.kube/config:ro" devopssentinel-web:1.0.0
```

### Running natively on WSL / Linux (no container)

The container is the easiest path, but the backend runs directly on a Linux host
too — which is what you want if the engine, `kubectl` and your kubeconfig all
live in WSL. It picks the same cluster by itself:

```bash
cd devopssentinel-web
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

cd backend
PYTHONPATH="$PWD" \
DSWEB_ENGINE_PATH="$PWD/../../DevOps_K8s_Sentinel_FINAL_GP.sh" \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Running natively, the endpoint the app should use is **loopback** — the cluster's
published port is on the same machine — so it probes `127.0.0.1` and `localhost`
first and only then the Docker-host aliases. That matters on WSL, where
`host.docker.internal` resolves to the Windows LAN address that the Windows
firewall blocks; without loopback the app would connect by routing every API call
out of WSL to Windows and back. Inside a container the order is reversed, because
`127.0.0.1` there is the container itself.

`kubectl` and `bash` must be on `PATH`. `python3-venv` is needed for the venv
step (`apt install python3.12-venv`); without it,
`pip install --target ~/dsweb-libs` plus `PYTHONPATH=~/dsweb-libs` works the same.

If the cluster is not found, `GET /api/v1/connections/discover` lists every
endpoint that answered `/version`, with the host, the source (docker or sweep)
and the container behind it — enough to see which host is missing.

### The console connects to your cluster by itself

You should not have to configure anything before data appears. On startup, and
again when the page loads if the connection is still missing, the console
detects a reachable cluster and connects to it:

* it inspects the Docker socket for Kubernetes containers (vcluster, kind, k3s,
  minikube, kube-apiserver, …) and reads their published host ports,
* it sweeps the usual API-server ports on `host.docker.internal` and the default
  gateway, keeping only ports that answer `/version`,
* it re-probes each of those with your kubeconfig's credentials, and activates
  the first pairing that authenticates.

That endpoint step is what makes a **vcluster** work. A vcluster kubeconfig
names `https://localhost:10093` — the port-forward `vcluster connect` opens on
your workstation — and inside a container `localhost` is the container itself.
The console finds the cluster's real published port (for example
`host.docker.internal:11259`), pairs it with the mounted kubeconfig, and records
the override, which is why the top bar shows the context rather than a Connect
button.

For WSL the full set of mounts is:

```bash
docker run -d --name devopssentinel-web --restart unless-stopped -p 127.0.0.1:8765:8765 \
  -v "//var/run/docker.sock:/var/run/docker.sock:ro" \
  -v "$USERPROFILE/devopssentinel-kube:/host-kube:ro" \
  --group-add 0 devopssentinel-web:1.0.0
```

`/var/run/docker.sock` enables container-level discovery, `--group-add 0` lets
UID 10001 read it, and `/host-kube` holds the kubeconfig. Point
`devopssentinel-kube` at a directory containing a `config` file.

If it ever reports **UNREACHABLE**, the saved endpoint stopped answering — which
happens when the cluster restarts and the published port moves. Press **Connect**
in the top bar, or call `POST /api/v1/connections/auto`; both re-detect and
repair the connection. The `/settings` page shows every pairing attempt with its
own reason, so a failure names the credential/endpoint pair that failed.

Set `-e DSWEB_AUTOCONNECT=0` to turn the startup pass off.

The two opt-in live-data features stay OFF in the image. Turn them on at start-up with
`-e DSWEB_ENABLE_SQL_CONSOLE=1 -e DSWEB_ENABLE_KAFKA_TOPICS=1`, or at runtime with the
matching switch on the `/settings` page — the switch applies immediately and needs no
restart (each also needs a reachable database/broker).

#### Reaching a database that is only a ClusterIP

The SQL console runs its statement **server-side**, so the endpoint has to be reachable
*from the backend*. A `ClusterIP` Service is only routable inside the cluster, and the
container runs outside it — so a plain `ClusterIP` will time out. The console says so,
and names the fix. Either:

```bash
# forward the Service to the host (loopback only; no cluster change)
kubectl -n <namespace> port-forward svc/<service> 15432:5432
```

then connect to `host.docker.internal:15432` from the container, or `127.0.0.1:15432`
from a native run; or expose the Service as a `NodePort`/`LoadBalancer` and use the
node address. The `DevOpsSentinel Web` start-up helper
[`scripts/dsw-db-tunnel.sh`](scripts/dsw-db-tunnel.sh) wraps the port-forward with
`start` / `status` / `stop`.

Startup output:

```
DevOpsSentinel Web v1.0.0

Sentinel     v4.2.2        READY
Backend                    READY
Frontend                   READY
Kubernetes                 CONNECTED
Context                    vcluster-docker_dev
Namespace                  default
Mode                       SUPERVISION [READ ONLY]

Open:
http://127.0.0.1:8765
```

Requirements: Python 3.11+, Bash 4.4+, `kubectl`, `jq`, and an engine checkout one directory above
`devopssentinel-web/` (or next to the launcher). No sudo, no `/usr/local`, no cluster
deployment. Python and those tools are only needed for the host launcher — the Docker image
above bundles them and needs none of them on the host.

## Platform fixtures (optional)

Every domain page is driven by real cluster objects. If a namespace is empty, the corresponding page
legitimately reports nothing. To exercise **all** pages end to end, deploy the bundled fixtures:

```bash
scripts/platform-resources.sh up   default     # default namespace is `default`
scripts/platform-resources.sh down default     # one-command cleanup
scripts/platform-resources.sh pvc  <namespace> <name> [size]   # standalone PVC
```

This creates a labelled (`devopssentinel.io/platform=true`) set of *real* objects, using only images
already present in the cluster:

| Page | Fixture |
| --- | --- |
| Workloads / Pods / Events / Topology | `Deployment/platform-web` (podinfo) + `Deployment/platform-postgres` |
| Storage | `platform-data` (1Gi) and `platform-cache` (512Mi) bound by `platform-web`, plus `platform-postgres-data` (2Gi) and `platform-kafka-data` (2Gi) — every PVC reports its consuming pod |
| Network | `Service/platform-web`, `Service/postgres`, `Service/kafka` with live endpoints, plus NodePorts `30432` (PostgreSQL) and `30092` (Kafka) |
| Database | `Service/postgres` → ready endpoint from `--postgres-discovery`, and a **real seeded schema**: `platform_customers` (10), `platform_orders` (60), `platform_events` (60) and the view `v_customer_value` |
| Kafka | a real single-node **Kafka 3.9.1 (KRaft)** broker with topics `orders`, `payments`, `events` (3 partitions each), 25 records per topic and the `platform-reader` consumer group with committed offsets |
| PKI / TLS | `Secret/platform-tls` (locally generated, 365 days) plus a cert-manager-issued `platform-cert` / `platform-cert-tls` (90-day lifetime, self-signed `ClusterIssuer`) when cert-manager is installed |

PostgreSQL and Kafka both write to PersistentVolumes, so the seeded schema, topics
and offsets survive a pod or cluster restart. Re-seed at any time with:

```bash
scripts/seed-platform-data.sh default     # drops and recreates the platform schema
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

The platform fixtures are exposed for exactly this: **PostgreSQL at `<node-ip>:30432`** (database/user
`platform`) and **Kafka at `<node-ip>:30092`** with the topics `orders`, `payments` and `events`
(3 partitions each). The full contract — including what the allowlist does *not* protect against —
is in [`docs/SECURITY.md` §2a](docs/SECURITY.md).

Both tabs prefill the node address the backend reports (`nodeAddress` on `/api/v1/system`, `defaultHost`
on the two console probes), because a **NodePort answers on a node, not on `127.0.0.1`** — inside a
vcluster only the API port is published to the host, which is why the documented `127.0.0.1:30432` /
`127.0.0.1:30092` endpoints never answered. **Fill platform credentials** (Database) and **Use platform broker**
(Kafka) fill the whole endpoint in one click, and both pages print the address they are using.

`scripts/live-smoke.sh [namespace] [api-base]` proves the path end to end and prints what was written
and what the API read back: it applies/seeds the fixtures, inserts a marker batch, reads it back through
`POST /api/v1/database/query`, creates a topic, produces records, consumes them back, lists topics
through `POST /api/v1/kafka/topics`, and re-confirms that write statements and unreachable brokers are
rejected. It discovers the node address and the nodePort values from the cluster instead of assuming
them, so it survives a driver that reassigns ports.

## Build

```bash
./scripts/build.sh              # install, typecheck, test, build, package
./scripts/build.sh --skip-tests # faster local iteration
./scripts/test.sh               # pytest + vitest + Playwright + axe
```

### Running the backend tests directly

`pytest` is a test-only dependency, so it is deliberately not in
`backend/requirements.txt` (the runtime image stays minimal). Any venv works:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt pytest pytest-asyncio
.venv/bin/python -m pytest backend/tests -q
```

On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
`pytest-asyncio` is required — `pyproject.toml` sets `asyncio_mode = "auto"` and
the `Runner`/`kube` tests are `async def`.

`tests/test_route_coverage.py` is worth knowing about: it recomputes, from
source, how many backend routes have a real frontend consumer and fails if a
route loses its consumer or if the allowlist of accepted gaps goes stale. It is
what keeps the coverage figure in `docs/GUI_CLI_PARITY.md` honest, so a new
backend route without a UI is a test failure rather than a silent gap.

## What is implemented

| Area | Status |
| --- | --- |
| One-command launcher, 127.0.0.1 default, browser open (WSL-aware) | ✅ |
| FastAPI adapter, allowlisted operations, read-only guard | ✅ |
| Standard response envelope (schemaVersion, source, status, partial, durationMs, cacheAgeMs) | ✅ |
| Short-TTL cache with single-flight de-duplication + audit trail | ✅ |
| Central redaction (tokens, JWTs, bearer, URL creds, private keys, k=v secrets) | ✅ |
| Origin allowlist, security headers, CSP, request-size and read-only guards | ✅ |
| Dashboard (problem-first), Findings center, Workloads + Pods, Pod detail, Events | ✅ |
| **Log Viewer** (`/logs`) — pod, container, previous-instance, tail, time window (`5m…24h`), timestamps, wrap, level filter, search, download and a Follow poll (`GET /api/v1/logs`, `/containers`) | ✅ |
| **Resource Describe** (`/describe`) — read-only `describe` / `YAML` / `JSON` / events for one object, copy + download (`GET /api/v1/describe`); `Secret` is refused | ✅ |
| Topology graph (React Flow), impact/reverse dependencies, failure-path filter | ✅ |
| GitOps command center (sources → Kustomization → HelmRelease chain) | ✅ |
| PKI / TLS dashboard, expiry posture, consumer/reference tracing | ✅ |
| PKI / TLS **Secrets** tab — Secret inventory (`type`, `created`, key names, key count) with the joined certificate expiry for `kubernetes.io/tls` Secrets (`GET /api/v1/secrets`) | ✅ |
| Usage charts with a **minutes → hours → days** range selector (`1m…7d`) and an honest window caption | ✅ |
| Network services + endpoint gaps, Storage PVC centre (namespace, capacity, StorageClass, consuming pod) | ✅ |
| Database page: Services table, Data view (backing pods + PVCs), Report/Raw + availability panel | ✅ |
| Database page: **SQL** tab — opt-in read-only console with allowlist + server-forced read-only session | ✅ |
| Kafka page: Brokers table with bootstrap candidates, **Topics** tab (live listing + availability), Data view, Report/Raw | ✅ |
| Kafka page: **Topics** tab — opt-in live topic/partition listing via one Metadata request | ✅ |
| Application Profile / Smart Health report views | ✅ |
| Incident workspace (`/incidents/:id`), PRE/POST baseline comparison (`/baselines`), Exports page (`/exports`) | ✅ |
| Doctor capability matrix, Settings, pins, history, local exports (JSON/CSV/NDJSON) | ✅ |
| Command palette (Ctrl+K, `/`), keyboard chords (`g d`, `g p`, …) | ✅ |
| 8 professional themes (4 dark / 4 light, incl. a Kubernetes-Dashboard palette) + system auto, swatch picker | ✅ |
| Virtualized tables (5,000-row inventory test), status = icon + text + colour | ✅ |
| LIVE interval that actually re-reads every cluster-facing query, plus an explicit **Refresh now** | ✅ |
| Usage charts observe the Metrics API every 5 s while their page is open (labelled on the card, pausable), so a trend exists without turning LIVE on | ✅ |
| SSE endpoints for live refresh and streamed logs | ✅ |
| pytest (263), Vitest (69), Playwright smoke + axe (frontend-only, fixture-backed) | ✅ |
| Live TLS inspection, an unbounded log follower, DB/Kafka credential prompts | ⛔ CLI only (see parity matrix) |

See **[docs/FEATURE_PARITY_MATRIX.md](docs/FEATURE_PARITY_MATRIX.md)** for the complete
per-feature accounting — there is no silent feature loss.

## Interface & themes

A dense, calm operations surface with soft "bubble" geometry: pill navigation and controls, layered
elevation, blurred top bar and status bar, and rounded data surfaces. Eight themes ship built in,
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
| **Kubernetes** | light | flat Kubernetes-Dashboard look: `#f5f5f5` page, white bordered cards, indigo chrome band |

Plus **Follow system**, which resolves to Midnight/Kubernetes from the OS preference. The active theme
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

