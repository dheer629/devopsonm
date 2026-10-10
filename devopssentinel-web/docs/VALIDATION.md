# Validation

Recorded on Windows 11, Node v24.16.0, Python 3.12.10, Chromium 153 (Playwright 1.48+),
frontend served from the production `dist/` build.

## Layers

| Layer | Command | Result |
| --- | --- | --- |
| Backend unit + API contract | `python -m pytest -q` | **263 passed** |
| Frontend typecheck (strict) | `cd frontend && npm run typecheck` | **clean** |
| Frontend unit | `cd frontend && npx vitest run` | **69 passed** (11 files) |
| Frontend production build | `cd frontend && npm run build` | **built** (568.03 kB initial JS / 41.16 kB CSS; 176.93 kB / 8.25 kB gzip) |
| Browser E2E (dark + light) | `cd frontend && npx playwright test` | **90 passed** (45 tests × 2 themes) |
| Live refresh | `LIVE` interval + **Refresh now** in the top bar | **4 passed** — a 5 s tick re-reads `/api/v1/pods` with no interaction, in both themes |
| Accessibility (axe) | `cd frontend && npx playwright test e2e/a11y.spec.ts` | **28 passed** (14 routes × 2 themes) |
| Opt-in live data (real DB + broker) | `scripts/live-smoke.sh default` | **PASSED** — see *Opt-in live data validation* |
| Live usage metrics (real cluster) | `curl /api/v1/metrics/nodes` + `/metrics/pods` against the dev cluster | **LIVE** — metrics-server v0.7.2 installed into `kube-system`; node `dev` 209 m / 1.75 GiB (23 %); per-pod CPU/memory for all seven `flux-system` controllers, charted in the GUI |
| Metrics API absent (real cluster) | the same two endpoints with no metrics-server in the cluster | **UNAVAILABLE** envelope (not a 500), and the page states it and draws no chart — see *Metrics-server* below |
| ClusterIP-only database reached from outside the cluster | `scripts/dsw-db-tunnel.sh` + `POST /api/v1/database/query` | **LIVE** — `svc/postgres` (a ClusterIP, so not routable from the container) forwarded to the host; the console returned real `information_schema` rows through `host.docker.internal:15432`, and the same query rendered 50 rows in the browser |
| Live server smoke | `uvicorn app.main:app` + HTTP checks | `/api/v1/version` 200, `/api/v1/system` 200, `/` and `/workloads` 200, fail-safe operation returns `UNAVAILABLE` envelope (not 500) |

### Metrics-server

`GET /api/v1/metrics/nodes` and `/metrics/pods` are two read-only `kubectl top` calls, so live usage
needs a Metrics API in the cluster. The dev cluster had none, which made the *absence* path the
default and left the *present* path unexercised — that is how the chart defect below went unnoticed.

Installed for this validation:

```bash
curl -sSLo /tmp/metrics-server.yaml \
  https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml

# k3s serves the kubelet on a self-signed certificate, so trust it explicitly.
sed -i 's|^        - --cert-dir=/tmp$|        - --cert-dir=/tmp\n        - --kubelet-insecure-tls|' \
  /tmp/metrics-server.yaml

kubectl apply -f /tmp/metrics-server.yaml
kubectl -n kube-system rollout status deploy/metrics-server
kubectl top nodes          # dev  209m  1%  1.7Gi  23%
```

Remove it again with `kubectl delete -f /tmp/metrics-server.yaml`; the app then returns to the
`UNAVAILABLE` path with no change of behaviour on its side.

`--kubelet-insecure-tls` skips verification of the kubelet's serving certificate. That is acceptable
for a throwaway single-node k3s cluster and is **not** a production recommendation — a real cluster
should have metrics-server trust the kubelet CA instead.

### Defects found and fixed during validation

| Defect | How it was found | Fix |
| --- | --- | --- |
| SPA catch-all route broke app construction once `frontend/dist` existed (`FileResponse \| JSONResponse` is not a valid response field) | pytest failed as soon as the frontend was built | `response_model=None` on the SPA routes + regression test |
| `status: "UNAVAILABLE"` was missing from the envelope `Status` literal → HTTP 500 on the missing-engine path | live server smoke test | added to the literal + `test_engine_unavailable_yields_envelope_not_500` |
| LIVE-refresh `Select` trigger had no accessible name (`button-name`, critical) | axe in both themes | `aria-label` on all select triggers |
| Fixture served the GitOps list for `/graph/gitops`, crashing the GitOps page | Playwright | reordered fixture matching + defensive graph shape guards in `GitOpsPage`/`TopologyPage` |
| Semantic colours used as *text* on their own 10 % tint failed AA in the light palette (success badge 4.38:1, active nav item 4.17:1, accent badge 4.12:1) | axe, once the light palette became the `desktop-light` project's theme | darkened the light theme's accent/domain/severity tokens; the vivid Kubernetes blue is kept on the chrome band, which carries white text |
| The generic `/pods` fixture rule shadowed `/metrics/pods` and returned the wrong envelope shape → the Workloads page threw and unmounted | Playwright (blank page + 30 s click timeout) | metrics routes matched first + defensive optional chaining on the metrics payload |
| The Memory (bytes) column was **silently clipped** (no overflow, so no scrollbar) at 9 columns | measuring `scrollWidth` vs `clientWidth` on the table region | `min-w-full` on the table + `shrink-0` on the usage label |
| New theme default was a fixed light palette, so both Playwright projects rendered the same theme | reviewing which theme each project actually exercised | default is now `system`, so `desktop-dark` tests midnight and `desktop-light` tests the light palette |
| The `LIVE` interval was **decorative**: `live`/`liveActive` were read only by the status bar, so no query ever set `refetchInterval` and nothing refreshed | tracing the selector through `AppContext` | a `LiveRefresher` component re-reads every active cluster-facing query on the tick (`refetchQueries` deliberately bypasses `staleTime`), plus an explicit **Refresh now** button; two Playwright tests pin both paths in both themes |
| The usage charts **invented a measurement**. An `UNAVAILABLE` metrics envelope still carries a fresh timestamp, so `useUsageHistory` appended a zero sample that no `kubectl top` ever reported; the chart then drew a fabricated `ceiling = 1` axis (`0.001` cores, `1 B`, `0.6699999999999999 B`), captioned it "**1 samples** over 0s", and left the honest `emptyMessage` unreachable | reading the rendered DOM with Playwright against the live app, after `kubectl top nodes` proved the cluster had no metrics-server — the page *looked* like it had one sample | chart only what was measured (`source === "LIVE"`); an all-zero series labels its axis `0` instead of a fabricated ceiling; `rangeSummary` pluralises; `formatBytes` rounds sub-KiB tick interpolation; 11 regression tests (`Usage.test.tsx`) |
| `/events` **crashed on its live path**. The route had two branches returning different shapes: the `kubectl` branch returned a *bare* envelope, the engine fallback returned `{envelope, raw, exitStatus}`. The page reads `data.envelope`, so it threw `Cannot read properties of undefined (reading 'data')` whenever the live branch won — which is the normal case on a connected cluster | user's screenshot, then an audit of all 24 operation routes against the live API: 23 conformed, `/events` did not | both branches return the operation shape; `kube.events_with_raw()` returns the command's stdout alongside the rows so `raw` stays truthful instead of empty; a contract test over every operation route, plus one test per `/events` branch |
| The SQL console **prefilled a fixture endpoint and stated it as fact**. It hardcoded `172.18.0.2:30432` with db/user `platform` from the E2E platform fixture and told the operator "The bundled platform database is …", so on a cluster without that NodePort every query failed. The disabled hint also said to "restart the backend with `DSWEB_ENABLE_SQL_CONSOLE=1`", while `liveconfig` applies the Settings switch live; and the *Row-level data* tile read "CLI ONLY" although the engine's read-only path needs `psql`, which is not in the image | user's screenshot, then `kubectl get svc -A` showed **no NodePort at all** (the only database is `postgres`, a ClusterIP at `10.102.76.185:5432`), and a TCP probe from inside the container showed every candidate address unreachable | the console prefills from the Service the cluster actually reports (`suggestSqlTarget`), states when a ClusterIP is only reachable in-cluster, leaves credentials blank, labels the fixture button as a fixture, and the hint names the Settings switch that needs no restart; the row-level tile reads `UNAVAILABLE` when neither path exists; 6 frontend + 1 backend regression tests |
| The SQL console and the Kafka topic lister prefilled `127.0.0.1`, which **never answers for a NodePort** — both timed out (`Connection refused` / 15 s timeout) inside the vcluster | user report (`/database`, `/kafka`) | the backend reports the node InternalIP as `nodeAddress` on `/system` and `defaultHost` on both console probes (one read-only `kubectl get nodes`); both views prefill it and print the reachable endpoint |
| The app **refused its own origin** on any port but the default. `DSWEB_PORT=8766` (the WSL run) and `--port N` moved the page to an origin the allow-list did not contain, so every GET succeeded and **every POST was `403 origin not allowed`** — the console looked connected while nothing could be saved, refreshed or connected | user's screenshot (`/database` on `:8766`, `origin not allowed` under *Run read-only query*), then `curl` with `Origin: http://127.0.0.1:8766` against the live backend | the serving origin is derived from `DSWEB_HOST`/`DSWEB_PORT` and always trusted (`config.self_origins`); the 403 body names the trusted origins so the mismatch is diagnosable from the page; `DSWEB_ALLOWED_ORIGINS` still narrows everything else and the list is never a wildcard; 7 `test_config.py` + 1 API regression test |
| The *Fill E2E platform fixture* button produced an endpoint that **exists nowhere**: it set only the fixture *port* while the host stayed the discovered ClusterIP, so the fields showed `10.102.76.185:30432`. A `useEffect` that re-applied the discovered values never re-ran (its dependencies had not changed), so the hybrid could not correct itself | user's screenshot, which showed the discovered `ClusterIP … :5432` in the explanatory line and `30432` in the port field | the fixture fills a **complete** fixture endpoint (its own host *and* port, from the node address) and the page says the values came from the fixture; the two fields are one piece of state with no effect to fall out of sync, plus a *Use the discovered endpoint* reset; 3 `live.test.ts` + 5 `SqlConsole.test.tsx` regression tests (the first component test of a page in this project) |
| The primary button was **unreadable in four of the eight themes**: `bg-accent text-white` on a light accent is **2.8:1** (midnight `#4c9aff`), far below AA for a 12.5 px label. It had never been seen because the only primary buttons sit behind the SQL-console tab and on `/settings`, and the Settings page was dying behind the `ErrorBoundary` before axe ever rendered it | axe on `/settings` in the dark project, once the page rendered again | the colour that sits *on* the accent is now a theme token (`--accent-ink`: near-black on the four light accents, white on the four dark ones) used by the `primary` variant — the dark themes now measure 6.6–9.4:1 |
| The E2E fixture answered **every unrouted request with an empty envelope** (`{data: null}`), a shape no backend route returns. Pages that read one level deeper (`SettingsPage` → `.active`, `PkiPage` → `.envelope.data`, `StoragePage` → `.envelope.data.warnings`) threw and blanked behind the `ErrorBoundary`, so six Playwright tests failed on *missing text* rather than on the real cause | the `error-context.md` snapshots reading *"Settings failed to render — Cannot read properties of null (reading 'active')"* | the fixture mocks the routes those pages load (`/connections`, `/storage/mount-warnings`, `/certificates/{expiry,duplicates,issuers}`, `/search`, `/network/endpoints`, `/settings/live`) and an unmocked route now returns **404**, naming the gap instead of handing a page a shape it cannot read |
| Two Playwright tests were measuring the **scheduler, not the feature**: `g d` arms the chord for 900 ms and Ctrl+K is only handled once the shell has mounted, yet the tests sent the keys between two separate CDP round-trips — and, for the palette, before the shell mounted. The palette test also looked for `getByLabel("Search", { exact: true })`, a label the input has not had for several revisions | the chord test passed alone (11.2 s) and failed in all four full-suite runs; a diagnostic probe proved the palette *does* open, that its input is labelled `Search resources and commands`, and that no keydown is swallowed | both tests wait for the shell to render and retry the *gesture* (`expect(…).toPass`), so a keystroke lost to the mount race is re-sent instead of failing the assertion; the palette locator names the real label |
| The usage charts **never showed history unless the operator had already turned `LIVE` on**. A metrics read is one instantaneous value, so a second sample only exists if something re-reads — and `LIVE` defaults to OFF. A 15-minute window therefore drew a single dot captioned "1 sample over 0s", with nothing on the page explaining why, so the feature read as broken | user's screenshot of `/workloads` (`LIVE OFF`, `1 sample over 0s`); three manual `GET /api/v1/metrics/nodes` proved the backend stamps every read (`source=LIVE`, a new `timestamp`), and a browser probe proved the chart does accumulate once `LIVE` is on (3 samples over 10 s → 6 over 25 s) | the charts now **observe on their own**: while their page is open they re-read the two metrics endpoints every 5 s, the card states `observing every 5s` beside its sample caption with a **Pause/Observe** control (remembered per browser), and pausing stops the sampling without discarding what was already collected; the E2E fixture now stamps each metrics response like the real endpoint, so the harness can exercise accumulation at all; 3 `observation.test.ts` + 2 `ObservationControl` tests + one Playwright test pinning the reads, the pause and the resume |

## What the backend suite proves

* `test_security.py` — bearer/JWT/URL-credential/PEM/k=v redaction, DNS-1123 and context validation,
  read-only verb guard, origin allowlist, tail bounds.
* `test_config.py` — the origin allow-list always contains the origin the app is *served on*
  (`DSWEB_HOST`/`DSWEB_PORT`), for a loopback bind, a wildcard bind and a named host, without ever
  becoming a wildcard.
* `test_runner.py` — argv construction, `--json` parsing, stdout redaction, timeout + child
  termination, missing interpreter, tolerant JSON parsing.
* `test_parsers.py` — pods, workloads, certificates (status derived from remaining days), GitOps
  readiness, services + endpoint gaps, PVCs, findings (resource extraction + domain guess),
  capabilities, dependency graph edges, log levels + repeated-pattern aggregation.
* `test_api.py` — envelope shape on every core route, cache marking, exit-code → status mapping,
  secret non-leakage, `/exec`/`/shell`/`/kubectl` returning 404, origin guard blocking unknown
  origins and allowing localhost, invalid namespace rejected with 400, CSV export, security headers,
  baselines and notes round-trips, diagnostics.

## What the browser suite proves

* Problem-first dashboard renders with read-only supervision visible.
* Workload grid → pod detail navigation, including the explicit `PARTIAL` log banner.
* Findings center orders CRITICAL first and renders glyph + label (not colour alone).
* Command palette opens with `Ctrl+K` and finds resources.
* GitOps page exposes **no** Reconcile/Suspend/Resume/Rollback/Upgrade control.
* PKI posture, topology inspector, storage/network inventories, doctor matrix, settings exports.
* Database and Kafka pages render parsed tables, a **Data** view joining each service to its backing
  pods/PVCs, and an explicit availability panel that states what row-level / topic data can and
  cannot be read (and the exact console command).
* Unknown routes render an explicit `UNAVAILABLE` state; refresh preserves the route; `g d` chord
  navigates.
* Incident workspace shows `INCIDENT MODE`, keeps operator notes local and lists evidence files.
* PRE/POST page captures a baseline, compares it and classifies changes (`DEGRADED`/`UNCHANGED`).
* Exports page offers only structured downloads and states that screenshots are not used.
* axe reports zero serious/critical violations on 10 routes in both dark and light themes.

## Live cluster validation (executed)

Verified against a real vcluster (`kubernetes-super-admin@dev`, node `dev`, v1.30.4) running in
Docker under WSL2, with the app served from WSL and Chrome on Windows.

| Check | Result |
| --- | --- |
| Engine reachable (`--doctor`, `--resources`, `--gitops`) | ✅ real data |
| `GET /api/v1/contexts` | ✅ `["kubernetes-super-admin@dev"]` |
| `GET /api/v1/namespaces` | ✅ 6 namespaces |
| `GET /api/v1/pods` (flux-system) | ✅ `OK` / `LIVE` / 4 pods / 1132 ms |
| `GET /api/v1/findings` | ✅ `OK` / `LIVE` / 30 findings / 7790 ms |
| `GET /api/v1/gitops` | ✅ `WARNING` / `LIVE` / 8 objects / 1088 ms |
| Startup banner in WSL | ✅ `Kubernetes CONNECTED`, `SUPERVISION [READ ONLY]` |
| Chrome on Windows reaching `127.0.0.1:8765` | ✅ |

Real captured formats that the parsers were aligned to:

* `--resources` — TAB-separated `POD READY STATUS RESTARTS AGE CPU USED … NODE IP OWNER …`
* `--triage` — TAB-separated `SEVERITY CATEGORY RESOURCE ISSUE EVIDENCE NEXT CHECK`
* `--gitops` — `Kind/name [STATUS REASON]` blocks with indented `key=value` lines
* `--network` — `Service/<name> type=… clusterIP=… ports=…` + `EndpointSlice: … ready=N/M`
* `--doctor` — column-aligned `tool  STATUS` lines
* `--storage` — `STORAGE DEPENDENCY GRAPH` tree: `PVC/<name> phase=… requested=… capacity=…` then
  `├── PV: <pv> class=…` / `└── Pod: <pod> node=…`
* `--certificates` — `[STATE] <secret> | namespace=… | source=Secret/tls.crt certificate#N |
  daysLeft=N` block followed by `subject=` / `issuer=` / `serial=` / `notBefore=` / `notAfter=` /
  `sha256 Fingerprint=` / `X509v3 Subject Alternative Name:` lines, plus a `SECRET METADATA` table
  (`NAME TYPE CREATED KEY COUNT KEY NAMES`) and a `SECRET MOUNT REFERENCES` table
* `--postgres-discovery` / `--kafka-discovery` — TAB-separated `SERVICE TYPE …` tables (rendered as
  report text)

### Defects found and fixed during live validation

| Defect | How it was found | Fix |
| --- | --- | --- |
| Parsers assumed space-separated tables; the engine emits TAB-separated tables, so pods/certificates/PVCs came back empty | live capture | `split_row` is TAB-aware; header detection requires all-caps columns (so `SOURCE  pods  STATUS` is not a header) |
| GitOps report was a block format, not a table | live capture | dedicated block parser (`Kind/name [STATUS REASON]` + `key=value`), including multi-word `message=` values |
| Network report is a Service/EndpointSlice tree, not a table | live capture | regex tree parser that attaches `ready=N/M` to the owning service |
| Read-only kubectl guard rejected `--context X get namespaces` (it assumed the verb was at position 0) | live API call returned `UNAVAILABLE` | guard now skips global flags before matching the verb, and still blocks mutation verbs |
| Pods table invented its own restart threshold, contradicting the engine's triage | live comparison | readiness drives pod status; restart counts stay a column and findings come from the engine |
| First run showed an empty context selector | live browser check | the UI adopts the kubeconfig's current context automatically |
| `pydantic-settings` was not in the WSL dependency set | live start | added to `requirements.txt` install step |
| Topology demanded a typed resource name, so the page looked broken | live browser check | resource picker is populated from the cluster and auto-selects the first object; one-click GitOps-chain toggle |
| Themes had no default palette at first paint (`:root` lost its variables when per-theme classes were added) | axe flagged `color-contrast` on `/workloads` | Midnight is now the `:root` default and `index.html` ships `class="theme-midnight dark"` |
| Doctor table listed banner lines as capabilities | live doctor output | rows are filtered to known status tokens |
| Empty GitOps in a non-Flux namespace looked broken | live browser check | explicit hint plus a one-click switch to `flux-system` |
| Database / Kafka / Application Profile pages rendered a **blank white screen** | user report (`/database`) | the hooks typed report data as `string` while the backend returned `{title, lines}`, so `.split()` threw and React unmounted the tree. The backend now returns the report as one string, and the UI tolerates both shapes via `reportText()` |
| Every domain page reported no data | user report (PVC / PKI empty) | the engine **requires `--namespace` in non-interactive mode** and the UI never picked one, so every invocation exited 2. The top bar now adopts a default namespace automatically, and the envelope surfaces the engine's own stderr reason instead of a generic message |
| Storage page empty | live capture of `--storage` | the report is a **dependency tree**, not a table; added a tree parser (`PVC/name phase=… requested=… capacity=…` + `PV:` / `Pod:` children) with the table form kept as a fallback |
| PKI page empty | live capture of `--certificates` | TLS metadata is a **multi-line block** (`[OK] name \| namespace=… \| daysLeft=…` + `subject=` / `issuer=` / `notAfter=`), not a table; added a block parser and derived consumers from `SECRET MOUNT REFERENCES` |
| The Secret inventory returned only its **first** row | live `GET /api/v1/secrets` on the platform fixtures | redaction replaced the whole TAB row containing a `password` key with a single `[REDACTED]` token; `extract_tables` treats a one-cell line as the end of a table, so every later Secret was dropped. Redaction is now **cell-aware** for TAB rows (`security._redact_value`), pinned by `test_security.py::test_redact_keeps_tab_table_rows_intact` |
| `--capabilities` and `--certificates` returned “engine produced no machine-readable output” even though the engine emitted valid JSON | live API probe | backend redaction rewrote whole pretty-printed JSON lines that merely mentioned `TOKEN`, leaving unparseable JSON. Redaction now parses and redacts the JSON document, keeping the structure valid |

### Environment notes (not application defects)

* The vcluster container (`ghcr.io/loft-sh/vm-container`) crash-loops with
  `ERROR: this script needs /sys/fs/cgroup/cgroup.procs to be empty`; it exited with code 128 while
  validation was running. `docker start vcluster.cp.dev` brings it back and it then stays healthy.
  This is the local cluster's own entrypoint/cgroup issue, not DevOpsSentinel.
* The vcluster docker driver assigns a random host port when the container is recreated, so the
  kubeconfig `server:` URL goes stale. A fresh admin kubeconfig was extracted from
  `/var/lib/vcluster/kubeconfig.yaml` into `~/.kube/vcluster-dev.yaml` with the current port; the
  user's `~/.kube/config` was backed up before any edit.
* WSL Ubuntu had no `pip`/`python3-venv` (PEP 668 externally managed), so backend dependencies were
  installed into the user site with `get-pip.py --user --break-system-packages`.
* `certificate-authority-data` and `insecure-skip-tls-verify` are mutually exclusive in a kubeconfig,
  so refreshing the stale `server:` URL must drop the CA bundle rather than add the insecure flag
  alongside it.
* WSL occasionally tears the distro down between commands, which kills detached background
  processes. Long apply/seed/verify cycles are therefore run as a single script.


## Opt-in live data validation

The two opt-in features were validated against **real** infrastructure, not mocks. The platform
fixtures deploy a PostgreSQL 16 pod and a single-node Kafka 3.9.1 (KRaft) broker, both on
PersistentVolumes and exposed with NodePorts so the local adapter can reach them.

| Check | Command / probe | Result |
| --- | --- | --- |
| Flags are inert by default | `pytest tests/test_live.py -k disabled_by_default` | **403 + explicit reason**, no connection attempted |
| Kafka topic listing | `POST /api/v1/kafka/topics {"host":"172.18.0.2","port":30092}` | **200**, `events`, `orders`, `payments`, `audit-log`, `__consumer_offsets` — `source: LIVE` |
| SQL console returns real rows | `POST /api/v1/database/query` against the seeded schema | **200**, e.g. `information_schema.tables` → `platform_customers`, `platform_events`, `platform_orders`, `v_customer_value` |
| Aggregates work | `select status, count(*), sum(amount) from public.platform_orders group by status` | **200**, 6 rows with real totals |
| Write statements are rejected | `drop table public.platform_orders`, `update … set amount = 0` | **400** `only read-only statements are allowed: …` |
| Chained statements are rejected | `select 1; delete from public.platform_orders` | **400** `only one statement per request is allowed` |
| Literals are not mistaken for SQL | `select '; drop table x' as sneaky` | **200** — the literal is returned as data |
| Unreachable broker is reported, not hidden | `POST /api/v1/kafka/topics` on port 39999 | **400** `cannot reach the broker: [Errno 111] Connection refused` |
| Reachable endpoint is reported, not guessed | `GET /api/v1/database/console`, `/kafka/console` | `defaultHost: "172.18.0.2"` on both — the node the platform NodePorts answer on |
| Live end-to-end report | `scripts/live-smoke.sh default` | **PASSED** — applies/seeds the fixtures, inserts a 7-row marker batch, reads it back through the API (`SKU-sentinel-smoke-01` → 7 rows / 98.00), creates a marker topic, produces 5 records, consumes 3 back, lists it through the API and re-confirms the read-only guard |
| Doctor capability grid | `GET /api/v1/system` | **all 9 AVAILABLE**: engine, bash, kubectl, jq, openssl, flux, helm, psql, kafka |
| Doctor engine capability report | `GET /api/v1/doctor` | `psql`, `kafka-topics.sh`, `kafka-topics`, `kafka-consumer-groups.sh`, `kafka-consumer-groups`, API discovery, Flux CRDs, cert-manager CRDs and Metrics API all **AVAILABLE** |
| PKI includes a cert-manager certificate | `GET /api/v1/certificates` | `platform-cert-tls` (cert-manager, 89 days) and `platform-tls` (364 days), both `OK` |
| PKI exposes real X.509 detail | `GET /api/v1/certificates` | every row carries `serial`, `fingerprint`, `not_before`, `san` and `source` parsed from the engine's TLS metadata block |
| Secret inventory shows certificate expiry | `GET /api/v1/secrets` | one row per Secret (`type`, `created`, `key_count`, `keys`); `kubernetes.io/tls` rows carry the joined certificate `expires` / `days` / `status`, non-TLS rows report `days: null` |
| Storage reports consumers | `GET /api/v1/storage` | 4 Bound PVCs, each with its consuming pod |
| Log viewer contract | `pytest backend/tests/test_api.py -k logs` | one bounded `kubectl logs`; the RFC3339 prefix is split into a `ts` column, credentials are redacted, an unknown `since` and a missing namespace are rejected, and container discovery is `get pod -o json` |
| Resource description contract | `pytest backend/tests/test_api.py -k describe` | `describe` / `yaml` / `json` / `events` all reach the API; `Secret` is refused with `403` before kubectl is called; `test_kube.py` pins the allowlist so `describe Secret`, `get secret -o yaml` and `--follow` can never reach a process |
| Log viewer (live vcluster) | `GET /api/v1/logs` on `default/platform-kafka-…` | **LIVE** — 3 lines with real RFC3339 timestamps split into the `ts` column, container discovery returned `['kafka']`, `since`/`tail` echoed back, and the raw view shows `kubectl --context kubernetes-super-admin@dev -n default logs … --tail=5 --since=1h --timestamps=true`. `since=1d` is rejected with `400 unsupported since: '1d'` |
| Resource describe (live vcluster) | `GET /api/v1/describe` on real Pod / Deployment / Service | **LIVE** — Pod `describe` 76 lines, Pod `yaml` 148, Pod `json` 201; Deployment `describe` 43 / `yaml` 93; Service `describe` 16–18 lines; a missing object returns `400 Error from server (NotFound): services "does-not-exist" not found`; `kind=Secret` returns **403** before kubectl is reached |
| Metrics range selector (fixture-backed E2E) | Playwright `/workloads` | **PASS** — `1m…7d` selectable; switching to `1 hour` re-frames the chart and the caption reads `1 hour window · N samples over …`, so a wide window never implies unobserved history |
| Metric observation (live vcluster, `LIVE` off) | Playwright against `127.0.0.1:8766/workloads` with `dsweb.live=0` | **LIVE** — the card read `observing every 5s` while the LIVE switch read `OFF`; `/api/v1/metrics/nodes` was re-read with no interaction and the caption went `15 min window · 3 samples over 10s` (t+12 s) → `15 min window · 5 samples over 20s` (t+25 s); no page errors |

Five protocol/environment details cost real debugging time and are worth recording:

1. **Kafka 3.9 removed Metadata v0** (KIP-896). A version-0 request is accepted at the TCP level and
   then closed with no response; the adapter must ask for **version 1**, whose response adds a
   nullable `rack` per broker, a `controller_id` before the topic array and an `is_internal` flag per
   topic. `test_kafka_request_is_a_single_metadata_v1_call` pins this.
2. **KRaft storage must be formatted exactly once.** Re-running `kafka-storage.sh format -t <new-uuid>`
   against an already-formatted directory fails with
   `Invalid cluster.id in: meta.properties. Expected …, but read …`. With a PersistentVolume the
   broker now formats only when `meta.properties` is absent.
3. **The platform Postgres originally had no volume**, so its seeded schema vanished on every pod
   restart and the SQL console looked empty. Both Postgres and Kafka now persist to PVCs.
4. **The engine's PostgreSQL read-only session is interactive-only**, which is why the console is a
   separate, opt-in, allowlisted path rather than another engine operation.
5. **The platform endpoints are NodePorts, so they answer on a *node* — never on `127.0.0.1`.** Both views
   prefilled `window.location.hostname`, which can never work inside a vcluster because only the API
   port is published to the host. They now prefill the node InternalIP that `GET /api/v1/system`
   reports as `nodeAddress`, and both pages print the reachable `<node>:30432` / `<node>:30092`
   endpoint. `scripts/live-smoke.sh` discovers the node and the nodePort values rather than assuming
   them, so it keeps working when the driver assigns different ports.

## Reproduce everything

```bash
./scripts/test.sh
```
