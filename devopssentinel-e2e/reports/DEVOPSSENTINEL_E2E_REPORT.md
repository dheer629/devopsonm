# DevOpsSentinel real WSL E2E validation

Run: 20261003T160122Z; mode: FULL; context: `vcluster-docker_dev`.

Source SHA-256: `63a8d8937330a071221de3ccea9bfeccd1fac33965554fec9efc724a3ca4fbe5`.

Private evidence: `/home/dheer/.devopssentinel/real-e2e/20261003T160122Z`.

**Release gate: NOT APPROVED.** Review failures, blocked coverage and requirement traceability before deployment.

Counts: PASS=87, FAIL=0, BLOCKED=0, NOT_APPLICABLE=1

| ID | Domain | Test | Status | Detail |
|---|---|---|---|---|
| DS-E2E-001 | workloads | Healthy Deployment, probes and resources | PASS |  |
| DS-E2E-002 | workloads | StatefulSet and PVC template | PASS |  |
| DS-E2E-003 | workloads | DaemonSet desired/current/ready | PASS |  |
| DS-E2E-004 | workloads | ds-e2e-job-success | PASS |  |
| DS-E2E-005 | workloads | ds-e2e-job-failed | PASS |  |
| DS-E2E-006 | workloads | CronJob controller creates owned Job | PASS |  |
| DS-E2E-010 | workloads | ds-e2e-crash | PASS |  |
| DS-E2E-011 | workloads | ds-e2e-image | PASS |  |
| DS-E2E-012 | workloads | ds-e2e-missing-config | PASS |  |
| DS-E2E-013 | workloads | Impossible node selector; toleration preserved | PASS |  |
| DS-E2E-014 | workloads | Running Pod with failed readiness probe | PASS |  |
| DS-E2E-015 | workloads | Liveness failure and restart history | PASS |  |
| DS-E2E-016 | workloads | Startup probe and started state | PASS |  |
| DS-E2E-017 | workloads | Bounded 32Mi OOM failure | PASS |  |
| DS-E2E-020 | dependencies | ConfigMap reverse dependencies | PASS |  |
| DS-E2E-021 | dependencies | Secret reverse dependencies | PASS |  |
| DS-E2E-022 | dependencies | ServiceAccount reverse dependencies | PASS |  |
| DS-E2E-030 | networking | Service endpoints plus live HTTP | PASS |  |
| DS-E2E-031 | networking | Service without endpoints | PASS |  |
| DS-E2E-032 | networking | Named targetPort mapping | PASS |  |
| DS-E2E-033 | networking | Service target port mismatch | PASS |  |
| DS-E2E-034 | networking | Multiple services select same Deployment | PASS |  |
| DS-E2E-035 | networking | NetworkPolicy parsing | PASS |  |
| DS-E2E-036 | networking | Cross namespace isolation | PASS |  |
| DS-E2E-037 | networking | Real cluster DNS resolution | PASS |  |
| DS-E2E-038 | networking | Ingress API graph | PASS |  |
| DS-E2E-040 | storage | Bound PVC and PV ownership | PASS |  |
| DS-E2E-041 | storage | Pending PVC without StorageClass | PASS |  |
| DS-E2E-070 | workloads | Multi-container Pod and successful init | PASS |  |
| DS-E2E-071 | workloads | Init container failure | PASS |  |
| DS-E2E-072 | security | Live logs and credential redaction | PASS |  |
| DS-E2E-073 | events | Previous container logs | PASS |  |
| DS-E2E-074 | events | Actual Kubernetes failure event timeline | PASS |  |
| DS-E2E-076 | nodes | Real node capacity and scoped reservations | PASS |  |
| DS-E2E-050 | certificates | Valid TLS Secret metadata and healthy expiry | PASS |  |
| DS-E2E-051 | certificates | Real five-day certificate is critical | PASS |  |
| DS-E2E-052 | certificates | Historical X.509 certificate is expired | PASS |  |
| DS-E2E-053 | certificates | Complete multi-DNS and IP SAN parsing | PASS |  |
| DS-E2E-054 | certificates | Duplicate leaf fingerprint detection | PASS |  |
| DS-E2E-055 | certificates | Root/intermediate/leaf trust chain | PASS |  |
| DS-E2E-150 | certificates | Omitted intermediate fails trust verification | PASS |  |
| DS-E2E-151 | certificates | Root self-issuance and intermediate trust | PASS |  |
| DS-E2E-152 | certificates | Actual Secret volume/env and workload ownership | PASS |  |
| DS-E2E-153 | certificates | Actual TLS Pod and verified TLS 1.2/1.3 | PASS |  |
| DS-E2E-154 | certificates | TLS endpoint hostname mismatch fails | PASS |  |
| DS-E2E-155 | certificates | Untrusted CA fails live verification | PASS |  |
| DS-E2E-056 | certificates | Live TLS fingerprint matches mounted Secret | PASS |  |
| DS-E2E-057 | certificates | Different Ingress Secret produces factual mismatch | PASS |  |
| DS-E2E-058 | certificates | Secret rotation refresh and server reload | PASS |  |
| DS-E2E-059 | certificates | Real cert-manager issuance and CertificateRequest | PASS |  |
| DS-E2E-156 | certificates | Real cert-manager missing Issuer failure | PASS |  |
| DS-E2E-157 | certificates | Certificate JSON/export and private-key redaction | PASS |  |
| DS-E2E-158 | certificates | Future certificate validity is explicit | PASS |  |
| DS-E2E-060 | gitops | Suspended Flux resource | PASS |  |
| DS-E2E-061 | gitops | Failed local Git source with message and transition | PASS |  |
| DS-E2E-062 | gitops | Ready local Git source and exact artifact revision | PASS |  |
| DS-E2E-063 | gitops | Local Git Kustomization deploys a real workload | PASS |  |
| DS-E2E-064 | gitops | Failed Kustomization from missing path | PASS |  |
| DS-E2E-065 | gitops | Local Helm chart installs real Deployment and Service | PASS |  |
| DS-E2E-066 | gitops | Actual Helm template failure | PASS |  |
| DS-E2E-067 | gitops | GitOps source, inventory and Helm dependency graph | PASS |  |
| DS-E2E-068 | gitops | Second local commit, revision gap and recovery | PASS |  |
| DS-E2E-069 | gitops | Workload owner and exact Git revision mapping | PASS |  |
| DS-E2E-079 | database | PostgreSQL Service, endpoint and port discovery | PASS |  |
| DS-E2E-080 | database | PostgreSQL real read-only SELECTs and credential lifecycle | PASS |  |
| DS-E2E-081 | database | PostgreSQL wrong password, invalid database and unreachable service | PASS |  |
| DS-E2E-082 | database | PostgreSQL schema, row count and audit query capability | PASS |  |
| DS-E2E-083 | database | Kafka real broker, messages, topic and consumer group reports | PASS |  |
| DS-E2E-084 | database | Kafka consumer lag support | NOT_APPLICABLE | Consumer lag is conditional on product support in the request. Sentinel exposes connectivity, topic listing and group listing, but has no lag-report operation; real broker group/offset truth is retained in database/kafka-setup.txt. |
| DS-E2E-090 | experience | TXT/CSV/JSON/NDJSON exports of a live report | PASS |  |
| DS-E2E-091 | experience | Machine JSON schema and no-ANSI output | PASS |  |
| DS-E2E-092 | experience | NO_COLOR and --no-color produce zero ANSI | PASS |  |
| DS-E2E-093 | experience | Sentinel inventory equals Kubernetes API | PASS |  |
| DS-E2E-094 | experience | Dashboard renders at 80/100/120/160 columns | PASS |  |
| DS-E2E-095 | experience | Unicode and ASCII glyph modes | PASS |  |
| DS-E2E-096 | experience | Read-only guard blocks mutation verbs | PASS |  |
| DS-E2E-097 | experience | Global search across resource types | PASS |  |
| DS-E2E-098 | experience | Regex and case-insensitive search filter | PASS |  |
| DS-E2E-099 | experience | Pagination source with 75 real ConfigMaps | PASS |  |
| DS-E2E-100 | experience | Cache LIVE to CACHE to force refresh | PASS |  |
| DS-E2E-101 | experience | Triage identifies real fixture failures | PASS |  |
| DS-E2E-102 | experience | Forward and reverse dependency mapping | PASS |  |
| DS-E2E-103 | experience | Doctor reports real tool availability | PASS |  |
| DS-E2E-104 | experience | Performance report measures live collectors | PASS |  |
| DS-E2E-105 | experience | Evidence bundle with checksums and redaction | PASS |  |
| DS-E2E-106 | experience | Global canary and private-key leak scan | PASS |  |
| DS-E2E-107 | experience | Near-limit long name renders within width | PASS |  |
| DS-E2E-108 | experience | Incident session local evidence path | PASS |  |
