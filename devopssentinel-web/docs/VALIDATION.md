# Validation

Recorded on Windows 11, Node v24.16.0, Python 3.12.10, Chromium 153 (Playwright 1.48+),
frontend served from the production `dist/` build.

## Layers

| Layer | Command | Result |
| --- | --- | --- |
| Backend unit + API contract | `python -m pytest -q` | **64 passed** |
| Frontend typecheck (strict) | `cd frontend && npm run typecheck` | **clean** |
| Frontend unit | `cd frontend && npx vitest run` | **18 passed** (4 files) |
| Frontend production build | `cd frontend && npm run build` | **built** (840 kB JS / 43 kB CSS; 261 kB / 8 kB gzip) |
| Browser E2E (dark + light) | `cd frontend && npx playwright test` | **62 passed** (31 tests × 2 themes) |
| Accessibility (axe) | `cd frontend && npx playwright test e2e/a11y.spec.ts` | **20 passed** (10 routes × 2 themes) |
| Live server smoke | `uvicorn app.main:app` + HTTP checks | `/api/v1/version` 200, `/api/v1/system` 200, `/` and `/workloads` 200, fail-safe operation returns `UNAVAILABLE` envelope (not 500) |

### Defects found and fixed during validation

| Defect | How it was found | Fix |
| --- | --- | --- |
| SPA catch-all route broke app construction once `frontend/dist` existed (`FileResponse \| JSONResponse` is not a valid response field) | pytest failed as soon as the frontend was built | `response_model=None` on the SPA routes + regression test |
| `status: "UNAVAILABLE"` was missing from the envelope `Status` literal → HTTP 500 on the missing-engine path | live server smoke test | added to the literal + `test_engine_unavailable_yields_envelope_not_500` |
| LIVE-refresh `Select` trigger had no accessible name (`button-name`, critical) | axe in both themes | `aria-label` on all select triggers |
| Fixture served the GitOps list for `/graph/gitops`, crashing the GitOps page | Playwright | reordered fixture matching + defensive graph shape guards in `GitOpsPage`/`TopologyPage` |

## What the backend suite proves

* `test_security.py` — bearer/JWT/URL-credential/PEM/k=v redaction, DNS-1123 and context validation,
  read-only verb guard, origin allowlist, tail bounds.
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
  daysLeft=N` block followed by `subject=` / `issuer=` / `notAfter=` lines, plus a
  `SECRET METADATA` table and a `SECRET MOUNT REFERENCES` table
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
| Database / Kafka / ETDP pages rendered a **blank white screen** | user report (`/database`) | the hooks typed report data as `string` while the backend returned `{title, lines}`, so `.split()` threw and React unmounted the tree. The backend now returns the report as one string, and the UI tolerates both shapes via `reportText()` |
| Every domain page reported no data | user report (PVC / PKI empty) | the engine **requires `--namespace` in non-interactive mode** and the UI never picked one, so every invocation exited 2. The top bar now adopts a default namespace automatically, and the envelope surfaces the engine's own stderr reason instead of a generic message |
| Storage page empty | live capture of `--storage` | the report is a **dependency tree**, not a table; added a tree parser (`PVC/name phase=… requested=… capacity=…` + `PV:` / `Pod:` children) with the table form kept as a fallback |
| PKI page empty | live capture of `--certificates` | TLS metadata is a **multi-line block** (`[OK] name \| namespace=… \| daysLeft=…` + `subject=` / `issuer=` / `notAfter=`), not a table; added a block parser and derived consumers from `SECRET MOUNT REFERENCES` |
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


## Reproduce everything

```bash
./scripts/test.sh
```
