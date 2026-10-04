# DevOpsSentinel Web — Feature Parity Matrix

Engine under test: `DevOps_K8s_Sentinel_FINAL_GP.sh` **v4.2.2** (`ADVANCED-UX-READ-ONLY-PRODUCTION`).

Legend

| Status | Meaning |
| --- | --- |
| **SUPPORTED** | Reachable in the browser with typed data and a rendered UI |
| **PARTIAL** | Reachable, but with a documented limitation (e.g. report-derived rows, or raw text) |
| **CLI ONLY** | Deliberately not exposed to the browser; remains available in the engine console |
| **BLOCKED** | Not exposed because the browser must never perform that action |
| **NOT APPLICABLE** | Meaningless for a browser surface |

## 1. Report / scripted modes

| Engine mode | Web status | Route / operation | Notes |
| --- | --- | --- | --- |
| `--health` | PARTIAL | `/health` (`system.health`) | Plain report text rendered with raw view |
| `--resources` | SUPPORTED | `/workloads`, `/workloads/pods/:name` (`workloads.resources`) | Pods + workloads normalized to typed rows |
| `--gitops` | SUPPORTED | `/gitops` (`gitops.overview`) | Split by kind (sources, Kustomizations, HelmReleases) |
| `--gitops-graph` | SUPPORTED | `/gitops`, `/topology?graph=gitops` (`graph.gitops`) | Flux chain rendered as graph + edge list |
| `--certificates` | SUPPORTED | `/pki` (`pki.certificates`) | Expiry posture, consumers, duplicates/issuers endpoints |
| `--cert-expiry` | SUPPORTED | `/api/v1/certificates/expiry` (`pki.cert_expiry`) | Nearest-expiry ordering |
| `--triage` | SUPPORTED | `/findings`, `/events` (`workloads.triage`) | Findings queue + event table/timeline |
| `--triage-workload KIND/NAME` | SUPPORTED | `/workloads/pods/:name` (`workloads.triage_workload`) | Pod detail, containers, events, logs |
| `--network` | SUPPORTED | `/network` (`network.topology`) | Services, endpoint gaps, port path |
| `--storage` | SUPPORTED | `/storage` (`storage.dependencies`) | PVC centre: namespace, status, capacity, StorageClass, volume **and the consuming pod** |
| `--etdp` | PARTIAL | `/etdp` (`etdp.platform`) | Grouping text rendered; engine emits text, not grouped JSON |
| `--postgres-discovery` | SUPPORTED | `/database` (`database.postgres`, `database.services`) | **Services** table (service, type, port, cluster IP, ready endpoint, status), **Data** view joining each database to its backing pod + PVCs, **Report**/**Raw**. Row-level SQL stays CLI ONLY |
| `--kafka-discovery` | SUPPORTED | `/kafka` (`kafka.discovery`, `kafka.services`) | **Brokers** table with bootstrap candidates, **Topics** availability panel (CLI/broker status + exact command), **Data** view with backing pods, **Report**/**Raw** |
| `--doctor` | SUPPORTED | `/doctor` (`system.doctor`) | Capability matrix parsed into rows + raw view |
| `--capabilities` | SUPPORTED | `/api/v1/capabilities` (`system.capabilities`) | Parsed capability rows |
| `--dependency TYPE/NAME` | SUPPORTED | `/topology`, `/api/v1/graph/...`, `/api/v1/impact/...` | Graph, reverse dependencies, failure path |
| `--snapshot` | PARTIAL | `/api/v1/snapshot` (`system.snapshot`) | Raw lines |
| `--evidence ID` | SUPPORTED | `/evidence` (`evidence.create` + bundle browser) | Browse `~/.devopssentinel/evidence` |
| `--explain [TOPIC]` | CLI ONLY | — | Plain-text engine help; not part of the operations UI |
| `--self-test` | PARTIAL | `system.self_test` (operation registered) | Plain text; used by CI |
| `--live-validate` | PARTIAL | `system.live_validate` (operation registered) | Raw lines |
| `--performance` | PARTIAL | `/api/v1/diagnostics` | Adapter cache + audit timings |
| `--ui-debug` | NOT APPLICABLE | — | Terminal rendering diagnostics |
| `--version`, `--help` | SUPPORTED | `/api/v1/version`, `/settings` | Web / Engine / API schema versions displayed separately |
| Interactive dashboard (menu) | NOT APPLICABLE | — | Replaced by the browser UI |
| `--persona MODE` | NOT APPLICABLE | — | Terminal menu emphasis only |
| `--compact`, `--no-color`, `--quiet` | NOT APPLICABLE | — | Adapter always uses `--no-color --json` |
| `--kubeconfig`, `--output`, timeouts/thresholds | PARTIAL | `/settings`, `DSWEB_*` env | Scope + timeouts configurable; engine `--output` keeps its default root |

## 2. Interactive-only capabilities

| Capability | Web status | Why |
| --- | --- | --- |
| Interactive pod log follow / `previous` / container selection | PARTIAL | Adapter exposes report-captured lines with `PARTIAL` status and an explicit warning; the engine's live follower is CLI ONLY |
| Full log center (raw cache, summary, audit log) | PARTIAL | Audit trail + diagnostics exposed; terminal pager is CLI ONLY |
| Live TLS probe / certificate-vs-endpoint comparison | CLI ONLY | `POST /api/v1/tls/inspect` returns `UNAVAILABLE` with a reason instead of opening arbitrary sockets from browser input |
| Interactive read-only PostgreSQL session | CLI ONLY | Credentials must never traverse the browser. `/database` shows the Services table, the backing pods/PVCs and an explicit availability panel with the exact console command |
| Kafka interactive tools | CLI ONLY | Same reason. `/kafka` shows brokers, bootstrap candidates and a **Topics availability** panel that states what can and cannot be read |
| Incident session + exports under `~/.devopssentinel/evidence/ID` | SUPPORTED | `/incidents/:id` workspace (notes + evidence + pins + exports), `/evidence`, `/api/v1/notes/{id}`, `--incident` launcher flag |
| PRE / POST change validation | SUPPORTED | `/baselines` (`GET/POST /api/v1/baselines`, `POST /api/v1/baselines/compare`) with UNCHANGED / IMPROVED / DEGRADED / NEW / REMOVED classification |
| `export_center` | SUPPORTED | `/exports` page + `/settings` + `GET /api/v1/exports/{domain}` (JSON/CSV/NDJSON) |
| Global search | SUPPORTED | Command palette (Ctrl+K) + `GET /api/v1/search` |

## 3. Mutation capabilities (must never exist in the browser)

| Action | Status | Enforcement |
| --- | --- | --- |
| `kubectl apply/create/delete/patch/edit/scale/replace/rollout` | BLOCKED | Read-only verb guard + no such operation id |
| Flux `reconcile` / `suspend` / `resume` | BLOCKED | Verb guard; no UI control exists (asserted by E2E) |
| Helm `install/upgrade/rollback/uninstall` | BLOCKED | Verb guard |
| Arbitrary shell / `exec` | BLOCKED | No endpoint; `/api/v1/exec`, `/shell`, `/kubectl` assert 404 |
| Git commit/push | BLOCKED | Not present in the adapter |
| Reading Secret payloads / private keys | BLOCKED | Redaction + engine contract; UI never requests them |

## 4. Cross-cutting engine guarantees

| Guarantee | Web status |
| --- | --- |
| No sudo, no `/usr/local`, no cluster installation | SUPPORTED (launcher enforces) |
| Local-only bind (127.0.0.1) | SUPPORTED (`--listen` requires `--token`) |
| Secret redaction | SUPPORTED (engine redaction + independent backend redaction) |
| Exit-code semantics | SUPPORTED (mapped to envelope status) |
| Timeouts / bounded operations | SUPPORTED (≤ 300 s, per-operation defaults) |
| Explicit missing-permission reporting | SUPPORTED (errors/warnings surfaced, never shown as zero) |
| Deterministic, no-hang behaviour | SUPPORTED (bounded waits, child termination on timeout) |

## 5. Deliberate additions (not in the engine)

| Addition | Rationale |
| --- | --- |
| `GET /api/v1/contexts`, `/namespaces` | Two narrowly-scoped read-only kubectl discovery calls; the engine exposes no list mode |
| `GET /api/v1/database/services`, `/kafka/services` | Structured views of the engine's own discovery tables (metadata only) so the pages can render tables instead of raw text |
| `GET /api/v1/system`, `/session`, `/diagnostics` | Web-only surface (versions, cache stats, audit trail) |
| Pins, history, notes, baselines | Local operator convenience under `~/.devopssentinel-web` |
| Export formatting (CSV/NDJSON) | Browser download convenience; values come from the engine unchanged |

## 6. Summary

| Status | Count |
| --- | --- |
| SUPPORTED | 20 |
| PARTIAL | 9 |
| CLI ONLY | 4 |
| BLOCKED | 6 |
| NOT APPLICABLE | 4 |

No engine capability is silently dropped: every row above is either reachable, explicitly
downgraded with a reason, or intentionally blocked.

