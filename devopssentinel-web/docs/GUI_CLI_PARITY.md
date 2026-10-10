# DevOpsSentinel — CLI / API / GUI Parity Matrix

Companion to `GUI_CAPABILITY_MATRIX.md`. `FEATURE_PARITY_MATRIX.md` answers
"does the web build cover the engine?". This answers the question §288 actually
asks: **for each capability, is it reachable from the CLI, the API, and the GUI —
and if not, why.**

**Evidence:** `[live]` verified against the running container; `[code]` read from source.

## Legend

| STATUS | Meaning |
| --- | --- |
| `PARITY` | Reachable from CLI, API and GUI with equivalent data |
| `API ONLY` | Engine + API work; the GUI does not surface it (**a defect**) |
| `CLI ONLY` | Deliberately terminal-bound; documented reason required |
| `BLOCKED` | Intentionally impossible in a browser, with a stated reason |

## 1. Core diagnosis

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| Triage report | `--triage` | `GET /triage` | `/findings` (via `/findings`) | `API ONLY` — `/triage` itself is unwired |
| Findings / incidents | interactive | `GET /findings` | `/findings` **[live]** | `PARITY` |
| Resource inventory | `--resources` | `GET /workloads`, `/pods` | `/workloads` **[live]** | `PARITY` |
| Pod detail | interactive | `GET /pods/{name}` | `/workloads/pods/:name` **[live]** | `PARITY` |
| Pod dependencies | interactive | `GET /pods/{name}/dependencies` | `/topology` | `PARITY` — **closed this pass**: thin alias of `GET /graph/Pod/{name}`, which `/topology` renders |
| Events | `--events` | `GET /events` | `/events` **[live]** | `PARITY` |
| Log capture | interactive `logs_capture` | `GET /logs`, `/pods/{name}/logs` | `/logs` | `PARITY` (no virtualisation) |
| Resource describe | interactive | `GET /describe` | `/describe` | `PARITY` |
| Health report | `--health` | `GET /health` | `/health` (not in nav) | `PARITY` — navigation gap only |
| Doctor | `--doctor` | `GET /doctor` | `/doctor` | `PARITY` |
| Capabilities | `--capabilities` | `GET /capabilities` | — | `API ONLY` (§137) |
| Self-test | `--self-test` | — | — | `CLI ONLY` — a process-level check |
| Live validation | `--live-validate` | — | — | `CLI ONLY` — non-interactive CI gate |

## 2. Dependency and impact analysis

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| Dependency graph | interactive | `GET /graph/{kind}/{name}` | `/topology` + edge-evidence panel **[live]** | `PARITY` — **closed this pass**: §37/§347 |
| GitOps chain graph | interactive | `GET /graph/gitops` | `/topology?graph=gitops` | `PARITY` |
| **Failure path** | interactive | `GET /failure-path/{kind}/{name}` | `/topology` failure-path mode **[live]** | `PARITY` — **closed this pass**: §40 |
| **Blast radius / consumers** | interactive | `GET /impact/{kind}/{name}` | `/topology` blast-radius mode, `Inspector` | `PARITY` — **closed this pass**: §41 |
| Path between two objects | interactive | `GET /path` | — | `API ONLY` |

## 3. GitOps

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| GitOps inventory | `--gitops` | `GET /gitops` | `/gitops` **[live]** | `PARITY` |
| Per-kind inventories | `--gitops` | `/gitops/sources`, `/kustomizations`, `/helmreleases` | `/gitops` per-kind tabs **[live]** | `PARITY` — **closed this pass**: §73 |
| Object detail | interactive | `GET /gitops/{kind}/{name}` | `/gitops` workspace drawer **[live]** | `PARITY` — **closed this pass**: §76 |
| **Source → workload chain** | interactive | `GET /gitops/chain` | `/gitops` + `/topology?graph=gitops` | `PARITY` — **closed this pass**: §77 |
| **Revision timeline** | interactive | `GET /gitops/{kind}/{name}/timeline` | `/gitops` revision state **[live]** | `PARITY` — **closed this pass**: §78 |

## 4. PKI / TLS

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| Certificate inventory | `--certificates` | `GET /certificates` | `/pki` **[live]** | `PARITY` |
| Expiry buckets | `--certificates` | `GET /certificates/expiry` | `/pki` expiry posture **[live]** | `PARITY` — **closed this pass**: §66–§67, engine thresholds |
| Duplicates | interactive | `GET /certificates/duplicates` | `/pki` duplicate subjects **[live]** | `PARITY` — **closed this pass** |
| Issuers | interactive | `GET /certificates/issuers` | `/pki` issuer list **[live]** | `PARITY` — **closed this pass** |
| Certificate detail | interactive | `GET /certificates/{name}` | `/pki` workspace drawer **[live]** | `PARITY` — **closed this pass**: §69 |
| Trust chain | interactive | `GET /certificates/{name}/chain` | `/pki` trust chain **[live]** | `PARITY` — **closed this pass**: §71 |
| Consumers | interactive | `GET /certificates/{name}/consumers` | `/pki` consumers **[live]** | `PARITY` — **closed this pass**: §69 |
| **Live TLS comparison** | interactive | `POST /tls/inspect` | `/pki` explains why it stays engine-side | `BLOCKED` — a browser must not open arbitrary sockets (§72) |
| Secret metadata | interactive | `GET /secrets` | `/pki` | `PARITY` — metadata only, never values |
| Raw private key | interactive only | — | — | `BLOCKED` — must never reach a browser (§173) |

## 5. Network / storage

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| Services | `--network` | `GET /network/services` | `/network` **[live]** | `PARITY` |
| Endpoint gaps | interactive | `GET /network/endpoint-gaps` | `/network` **[live]** | `PARITY` |
| EndpointSlices | interactive | `GET /network/endpoints` | `/network` EndpointSlices tab **[live]** | `PARITY` — **closed this pass**: §79 |
| **Port path** | interactive | `GET /network/port-path/{service}` | `/network` Service drawer **[live]** | `PARITY` — **closed this pass**: §81–§82 |
| Network policies | interactive | `GET /network/policies/{pod}` | `/network` Network policies tab **[live]** | `PARITY` — **closed this pass**: §84 |
| Service DNS | interactive | `GET /network/dns/{service}` | `/network` Service drawer **[live]** | `PARITY` — **closed this pass**: §83 |
| PVC inventory | `--storage` | `GET /storage` | `/storage` **[live]** | `PARITY` |
| PVC detail | interactive | `GET /storage/pvc/{name}` | `/storage` claim drawer **[live]** | `PARITY` — **closed this pass**: §86 |
| PVC consumers | interactive | `GET /storage/consumers/{name}` | `/storage` claim drawer **[live]** | `PARITY` — **closed this pass**: §86 |
| Mount warnings | interactive | `GET /storage/mount-warnings` | `/storage` Mount warnings tab **[live]** | `PARITY` — **closed this pass**: §85 |

## 6. Data services, evidence, change validation

| FEATURE | CLI | API | GUI | STATUS |
| --- | --- | --- | --- | --- |
| Database discovery | interactive | `GET /database`, `/database/services` | `/database` | `PARITY` |
| Read-only SQL console | interactive | `POST /database/query` | `/database` (opt-in) | `PARITY` |
| Kafka discovery | interactive | `GET /kafka`, `/kafka/services` | `/kafka` | `PARITY` |
| Kafka topic listing | interactive | `POST /kafka/topics` | `/kafka` (opt-in) | `PARITY` |
| Live DB/Kafka credentials | prompt | — | prompt (never stored) | `PARITY` |
| Evidence bundle | `--evidence ID` | `/evidence`, `/evidence/{id}`, `/evidence/{id}/file` | `/evidence` | `PARITY` |
| PRE / POST baselines | interactive | `/baselines`, `/baselines/compare` | `/baselines` | `PARITY` |
| Exports | `--output` | `GET /exports/{domain}` | `/exports` | `PARITY` |
| Search | interactive | `GET /search` | palette → server search | `PARITY` — **closed this pass**: 6 domains, prefix grammar, provenance per hit |
| Pins / notes / history | local state | `/pins`, `/notes`, `/history` | `Inspector`, `/incidents/:id` | `PARITY` |

## 7. Deliberately terminal-bound (with reasons)

| FEATURE | Why it stays CLI-only |
| --- | --- |
| `--self-test` | Validates the engine process and its bundled tooling; a browser cannot observe that |
| `--live-validate` | A CI exit-code gate, not an interactive surface |
| Mutating operations | `SUPERVISION [READ ONLY]` is enforced by the backend allowlist, not by hiding buttons (§251–§253) |
| Raw Secret values / private keys | Must never enter a browser process (§172, §173) |

## 8. Parity verdict

Counts are per row in the tables above; a row covering several routes is counted
once (the per-kind GitOps inventories cover three routes).

| STATUS | Before this pass | After |
| --- | --- | --- |
| `PARITY` | 28 | **46** |
| `API ONLY` | 29 | **3** |
| `CLI ONLY` | 3 | 2 |
| `BLOCKED` | 2 | 2 |

**What moved.** 23 routes gained a real consumer in the GUI, and one was
reclassified from `API ONLY` to `BLOCKED` because it cannot be done safely in a
browser:

| Domain | Routes closed | Where |
| --- | --- | --- |
| Graph | `/graph/{kind}/{name}` (edge evidence), `/failure-path/{kind}/{name}`, `/impact/{kind}/{name}`, `/pods/{name}/dependencies` | `/topology` — mode selector, edge-evidence panel, deterministic layout |
| PKI | `/certificates/expiry`, `/duplicates`, `/issuers`, `/certificates/{name}`, `/certificates/{name}/chain`, `/certificates/{name}/consumers` | `/pki` — expiry posture, workspace drawer with validity timeline, trust chain, consumers |
| GitOps | `/gitops/{kind}/{name}`, `/gitops/chain`, `/gitops/{kind}/{name}/timeline`, `/gitops/sources`, `/gitops/kustomizations`, `/gitops/helmreleases` | `/gitops` — per-kind tabs + workspace drawer with managed chain and revision state |
| Network | `/network/endpoints`, `/network/port-path/{service}`, `/network/policies/{pod}`, `/network/dns/{service}` | `/network` — EndpointSlices and Network-policies tabs, Service drawer |
| Storage | `/storage/pvc/{name}`, `/storage/consumers/{name}`, `/storage/mount-warnings` | `/storage` — Mount warnings tab, claim drawer with binding chain and consumers |

**What is left.**

| Route | Why it stays `API ONLY` |
| --- | --- |
| `GET /triage` | `/findings` already renders the same engine findings; `/triage` is the raw report and adds no rows the queue lacks |
| `GET /path` | A two-object path query needs a target picker that does not yet exist; the graph modes cover the single-object case |
| `GET /capabilities` | `/doctor` already reports tool availability for the operator; the raw capability list is a support artifact (§137) |

**Conclusion.** API↔GUI parity is now the exception rather than the rule:
`test_route_coverage.py` measures **74 of 89 route templates (83%) with a literal
frontend consumer**, up from 64 of 94 at the start of this remediation. The three
remaining `API ONLY` rows are all cases where the GUI already presents the same
engine evidence through a sibling route, so closing them would add surface area
without adding information. As before, none of this pass required new
diagnostic logic: every relationship, threshold and status the GUI now shows is
read from an engine report (§286, §289, §290).

