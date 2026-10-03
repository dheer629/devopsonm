# DevOpsSentinel E2E — User Guide

A real-data, machine-asserted end-to-end test harness for the single-file
`DevOps_K8s_Sentinel_FINAL_GP.sh` console. It creates **actual** Kubernetes objects in a
**disposable local WSL cluster**, waits for **actual** Kubernetes states, runs the real
Sentinel, and compares the Sentinel's output with the Kubernetes API source of truth.
Nothing is mocked in E2E mode.

---

## 1. Safety model

* **Local-cluster gate.** `run_all.py` refuses to run unless: WSL is detected, the
  selected context equals the active context, the API server is loopback, the context is
  `vcluster-docker_dev`, the Docker container `vcluster.cp.dev` exists, and the cluster
  has exactly one node named `dev`. Any other context aborts with `SAFETY BLOCK`.
* **Isolation.** All fixtures live in four namespaces —
  `devopssentinel-e2e`, `devopssentinel-e2e-peer`, `devopssentinel-e2e-gitops`,
  `devopssentinel-e2e-pki` — and every object carries
  `devopssentinel.io/test-suite=true` and `app.kubernetes.io/part-of=devopssentinel-e2e`.
* **Scoped cleanup.** `cleanup.sh` deletes only those four namespaces, and refuses to
  delete a namespace that contains unowned objects.
* **Read-only product.** The Sentinel itself never mutates the cluster. Only the harness
  applies/deletes fixtures.

## 2. Requirements

| Tool | Why |
| --- | --- |
| WSL2 + Docker | the local vcluster runs as the `vcluster.cp.dev` container |
| `kubectl` | talks to the vcluster |
| `docker` | builds/imports the fixture image |
| `python3` (3.10+) | harness runtime |
| `openssl`, `jq`, `helm`, `flux` | Sentinel capabilities under test |
| internet (host) | pulls the pinned cert-manager manifest and images |

## 3. Layout

```
devopssentinel-e2e/
├── run-all.sh            # entry point -> run_all.py
├── cleanup.sh            # scoped cleanup -> run_all.py --cleanup-only
├── run_all.py            # Harness: safety gate, fixtures, cases, evidence, reports
├── workloads.py          # workloads, networking, storage, dependencies, logs, events
├── pki.py                # real X.509, TLS endpoints, cert-manager
├── gitops.py             # Flux GitRepository/Kustomization/HelmRelease (local git)
├── database.py           # PostgreSQL + Kafka, in-cluster client
├── experience.py         # UI, exports, search, cache, security, read-only guard
├── local_git_server.py   # cluster-internal git smart-HTTP + Helm chart fixture
├── Dockerfile            # ds-e2e-tools:local (bash, jq, openssl, git, git-daemon, psql)
├── COMMANDS.md           # step-by-step manual command list
├── gitops/README.md
└── reports/              # generated report, CSV, JSON, VALIDATION_SUMMARY.md
```

## 4. Quick start

```bash
ROOT='/mnt/c/Users/dheer/OneDrive/Desktop/AI Projects/DeVops_latest'; cd "$ROOT"
bash devopssentinel-e2e/run-all.sh --mode FULL --install-prereqs --keep
cat devopssentinel-e2e/reports/DEVOPSSENTINEL_E2E_REPORT.md
```

`--keep` leaves every fixture deployed. Drop it to auto-clean on success.

## 5. Modes and flags

| Flag | Meaning |
| --- | --- |
| `--mode QUICK\|STANDARD\|FULL` | suite breadth (default `FULL`) |
| `--install-prereqs` | install pinned cert-manager v1.15.3 if CRDs are missing |
| `--keep` | do not clean up fixtures afterwards |
| `--domain NAME` | run only one domain (repeatable) |
| `--test DS-E2E-NNN` | run only specific cases (repeatable) |
| `--failed` | re-run cases that failed/were blocked in the previous report |
| `--cleanup-only` | delete the four E2E namespaces |
| `--context NAME` | override the kubectl context |

Domains: `workloads` (also covers networking/storage/dependencies), `certificates`,
`gitops`, `database`, `experience`.

Environment: `KEEP_ON_FAILURE=1` keeps fixtures only when something failed.

## 6. What each outcome means

* **PASS** — fixture deployed **and** Kubernetes truth verified **and** Sentinel executed
  **and** Sentinel output machine-matched **and** evidence captured.
* **FAIL** — a real defect or an assertion mismatch.
* **BLOCKED** — a missing prerequisite or environment limit; always carries a reason and
  a next action. Never counted as a pass.
* **NOT_APPLICABLE** — outside the product's stated scope.

## 7. Evidence and reports

Per case: `~/.devopssentinel/real-e2e/<stamp>/<TEST-ID>/` with `result.json`,
`exception.txt` (on failure), fixture manifests, Kubernetes API JSON, and
`sentinel-*.stdout` / `sentinel-*.stderr`.

Published: `devopssentinel-e2e/reports/DEVOPSSENTINEL_E2E_REPORT.md`,
`..._RESULTS.csv`, `..._RESULTS.json`, `performance.json`.

## 8. Prerequisites and the previously blocked cases

The first FULL run left six cases BLOCKED. How each is now handled:

| ID | Was blocked by | Resolution |
| --- | --- | --- |
| DS-E2E-059, DS-E2E-156 | cert-manager CRDs absent | `--install-prereqs` installs pinned cert-manager **v1.15.3**; the tests then create a real self-signed `Issuer`, `Certificate` and `CertificateRequest`, and a controlled failing `Certificate`. |
| DS-E2E-080, DS-E2E-081 | Docker Desktop isolates container networking, so `docker run --network host` cannot reach a WSL-host `kubectl port-forward` | Replaced with an **in-cluster client pod** (`ds-e2e-pg-client`) that reaches `ds-e2e-postgres.devopssentinel-e2e.svc:5432` directly. |
| DS-E2E-082 | Sentinel exposed only four PostgreSQL menu options | Added a read-only **“Schema / row counts”** option to `pg_readonly_session` (exact per-table counts via `query_to_xml`); the integration script now drives and asserts it. |
| DS-E2E-083 | `apache/kafka:3.9.1` CLI JVM exited 139 (SIGSEGV) | Root cause: the Sentinel's `run_bounded` duplicates stdin for its children, and the harness piped the script via `bash -s`; every bounded child then exited 139. The harness now stages the runner as a **file** and executes it. Heap/memory were also raised (broker 256–512m, container 1536Mi). |

If you prefer to do it by hand, see **COMMANDS.md**.

## 9. Test catalog (highlights)

| Domain | IDs |
| --- | --- |
| workloads | 001–006 (Deployment/StatefulSet/DaemonSet/Job/CronJob), 010–017 (CrashLoop, ImagePull, ConfigError, Pending, probes, OOM), 070–076 (multi-container, init failure, logs, events, nodes) |
| dependencies | 020–022 (ConfigMap/Secret/ServiceAccount reverse edges) |
| networking | 030–038 (endpoints, zero endpoints, targetPort, PORT_MISMATCH, multiple services, NetworkPolicy, cross-namespace, DNS, Ingress) |
| storage | 040–041 (bound PVC + PV, pending PVC) |
| certificates | 050–059, 150–158 (valid/expiring/expired/SAN/duplicate/chain/incomplete, TLS server, match/mismatch, rotation, cert-manager) |
| gitops | 060–069 (suspended, failed source, ready source, Kustomization, Helm, graphs, revision change, ownership) |
| database | 079–084 (PostgreSQL discovery/sessions/failures/schema, Kafka) |
| experience | 090–108 (exports, machine JSON, NO_COLOR, widths, Unicode, read-only guard, search, filter, pagination, cache, triage, dependencies, doctor, performance, evidence, leak scan, long names, incident) |

## 10. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `SAFETY BLOCK` | not on the local disposable cluster — check `kubectl config current-context` |
| GitOps clones return HTTP 502 | `git-http-backend` missing → rebuild the tools image (`git-daemon` is in the Dockerfile) |
| Bounded child exits **139** | the Sentinel script was piped on stdin (`bash -s`); run it from a file or with `bash -c` |
| PostgreSQL “connection failed” | run the client **inside** the cluster; `docker run --network host` cannot reach a WSL port-forward |
| `docker build` fails on `apk add` | no internet from the Docker host |
| cert-manager never becomes Ready | `kubectl -n cert-manager get pods` and check image pulls |

## 11. Recommended workflow

1. `bash devopssentinel-e2e/run-all.sh --mode FULL --install-prereqs --keep`
2. Read `reports/DEVOPSSENTINEL_E2E_REPORT.md`.
3. For anything not PASS, open `~/.devopssentinel/real-e2e/<stamp>/<ID>/`.
4. Re-run just that domain with `--domain ... --keep`.
5. When finished: `bash devopssentinel-e2e/cleanup.sh`.

