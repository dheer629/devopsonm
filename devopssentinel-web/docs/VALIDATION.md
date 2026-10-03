# Validation

Recorded on Windows 11, Node v24.16.0, Python 3.12.10, Chromium 153 (Playwright 1.48+),
frontend served from the production `dist/` build.

## Layers

| Layer | Command | Result |
| --- | --- | --- |
| Backend unit + API contract | `python -m pytest -q` | **50 passed** |
| Frontend typecheck (strict) | `cd frontend && npm run typecheck` | **clean** |
| Frontend unit | `cd frontend && npx vitest run` | **18 passed** (4 files) |
| Frontend production build | `cd frontend && npm run build` | **built** (840 kB JS / 43 kB CSS; 261 kB / 8 kB gzip) |
| Browser E2E (dark + light) | `cd frontend && npx playwright test` | **46 passed** (23 tests × 2 themes) |
| Accessibility (axe) | `cd frontend && npx playwright test e2e/a11y.spec.ts` | **14 passed** (7 routes × 2 themes) |
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
* axe reports zero serious/critical violations on 7 routes in both dark and light themes.

## Cluster integration

The browser suite is deliberately **fixture-backed** so it runs in CI without a cluster. Real
cluster validation is performed by the existing DevOpsSentinel WSL harness:

```bash
cd ../devopssentinel-e2e && ./run-all.sh          # engine-level, disposable vcluster
bash ../scripts/test-faults.sh vcluster-docker_dev # CrashLoopBackOff, Pending PVC, TLS, canary
```

Run the web UI against the same disposable cluster to validate live behaviour:

```bash
# in WSL, with the disposable vcluster context active
./devopssentinel-web --context vcluster-docker_dev --namespace devopsonm
```

A live-cluster pass has **not** been executed in this environment (no WSL/kubectl available on the
Windows host that produced this build). The adapter fails safe: when the engine or bash is missing,
operations return `status: "UNAVAILABLE"` with a documented reason and the UI shows the error state
rather than fabricating data. This is the one acceptance item that remains open.

## Reproduce everything

```bash
./scripts/test.sh
```
