# DevOpsSentinel real-cluster E2E validation summary

Run `20261003T160122Z`, mode `FULL` with `--install-prereqs --keep`, context
`vcluster-docker_dev` (local Docker vcluster, Kubernetes v1.30.4, single node `dev`).
Validated utility SHA-256
`63a8d8937330a071221de3ccea9bfeccd1fac33965554fec9efc724a3ca4fbe5`.

## Result

| Outcome | Count |
| --- | --- |
| PASS | 86 |
| FAIL | 0 |
| BLOCKED | 0 |
| NOT_APPLICABLE | 1 |

All 86 runnable tests compared live Kubernetes API truth with the Sentinel's
own output, machine-asserted, with evidence captured per case under
`~/.devopssentinel/real-e2e/20261003T160122Z/`. No test was marked PASS from a
successful `kubectl apply` alone. Every previously BLOCKED case now PASSES, and
the run used `--keep`, so **all fixtures and cert-manager remain deployed** for
manual inspection.

Release gate: **NO FAILURES AND NO BLOCKED CASES REMAIN** for this disposable
local cluster. This is not a claim of universal production readiness; see the
coverage limits in `docs/VALIDATION.md`.

## Safety gate

The harness refuses to run unless the context is a disposable local cluster.
`vcluster-docker_dev` is a local vcluster in Docker; all fixtures were created
only in `devopssentinel-e2e*` namespaces, labelled
`devopssentinel.io/test-suite=true`. This run used `--keep`, so the fixtures and
the pinned cert-manager are still deployed; `cleanup.sh` removes only the four
E2E namespaces when you are finished.

## Defects found and fixed

### DevOpsSentinel (`DevOps_K8s_Sentinel_FINAL_GP.sh`, v4.2.2)

1. **GitOps failure misclassification (release-relevant).** A Flux resource
   whose `Ready` condition is `False` was labelled
   `WARN RECONCILIATION_PENDING` whenever the controller had also set
   `Reconciling=True` (its normal retry state), even though the summary line
   counted it `FAILED`. The `Reconciling` check ran before the `Ready=False`
   check. Reordered so a definitive `Ready=False` is always
   `FAIL RECONCILIATION_FAILED` / `FAIL HELM_FAILURE`; `Reconciling=True`
   without a failure remains `WARN RECONCILIATION_PENDING`.
   (DS-E2E-061/064/066)

2. **Network report lost capabilities during the 4.2.2 UX overhaul.**
   `service_topology_report` no longer surfaced NetworkPolicy objects, Ingress
   hosts, or Service targetPort mismatches, and `dns_inventory_report` had been
   removed. Restored: NetworkPolicy inventory, `hosts=` on Ingress edges,
   `PORT_MISMATCH` when a numeric `targetPort` is not declared by any selected
   Pod container, and a Service DNS inventory function.
   (DS-E2E-033/035/037/038)

### E2E harness (`devopssentinel-e2e/`)

3. **Missing `experience` module.** `run_all.py` imported a module that did not
   exist, so no UI/export/search/cache/security tests ever ran. Added
   `experience.py` (19 real-data cases: exports, machine JSON, NO_COLOR,
   inventory parity, 80/100/120/160 widths, Unicode/ASCII, read-only guard,
   search, regex filter, pagination with 75 real ConfigMaps, cache lifecycle,
   triage, dependency mapping, doctor, performance, evidence, leak scan, long
   names, incident session).

4. **`git-http-backend` absent in the fixture image.** Alpine 3.23's `git`
   package does not ship `git-http-backend`, so every Flux `GitRepository`
   clone failed with HTTP 502 and the whole GitOps domain failed. The
   `git-daemon` package provides it; added to the tools Dockerfile.
   (DS-E2E-062/063/065/067 now PASS)

5. **Cleanup refused a namespace containing a Flux-generated `HelmChart`.**
   `cleanup()` treated the controller-generated
   `helmcharts.source.toolkit.fluxcd.io/<ns>-<release>` object as unowned.
   Added a precise exception.

6. **Export test used a file outside `RUN_DIR`.** `_export_file_core` only
   accepts sources under `$RUN_DIR`; the PKI export test passed a temp file and
   silently failed. Now generated inside the runtime dir. (DS-E2E-157)

7. **Stale assertions for the 4.2.2 interface.** Updated the log-context and
   previous-log tests to the 4.2.2 `ui_log_context_report FILE PATTERN`
   signature, the network topology format (`ready=N/M`), the SecretRef graph
   label, and made crash/init/previous-log assertions retry (a crash-looping
   container briefly reports `Running` between restarts).

8. **Leak scan false positive.** The canary scan flagged raw Kubernetes API
   dumps (a fixture Pod spec legitimately contains its own canary command
   text). Scoped the scan to Sentinel-generated artifacts only.

9. **PostgreSQL fixture race.** The `postgres` entrypoint restarts the server
   after init, so the first truth query failed with exit 2. Added a bounded
   retry. (DS-E2E-079)

10. **PostgreSQL credential drift across runs.** The fixture regenerated the
    password each run but the `restartPolicy: Never` server was never recreated,
    so TCP authentication failed on every run after the first. The Secret is now
    reused when present and the running server's password is aligned over the
    trust-auth local socket (no deletion). (DS-E2E-080/081/082)

11. **Kafka CLI exited 139 (SIGSEGV).** Root cause: the Sentinel's `run_bounded`
    duplicates stdin for its children; the harness piped the runner script via
    `bash -s`, corrupting the script stream so *every* bounded child exited 139.
    The runner is now staged as a file and executed, and heap/memory were raised.
    (DS-E2E-083)

### DevOpsSentinel — PostgreSQL engine

12. **New read-only `Schema / row counts` option** in `pg_readonly_session`
    (exact per-table counts via `query_to_xml`), so schema discovery and row
    counts are available without leaving the read-only path. (DS-E2E-082)

## Previously blocked cases — now resolved

| ID | Was blocked by | Resolution | Now |
| --- | --- | --- | --- |
| DS-E2E-059 | cert-manager CRDs absent | pinned cert-manager **v1.15.3** installed (`--install-prereqs`) | PASS |
| DS-E2E-156 | cert-manager CRDs absent | as above | PASS |
| DS-E2E-080 | Docker Desktop isolates container networking from the WSL host | in-cluster client pod `ds-e2e-pg-client` reaches the Service directly | PASS |
| DS-E2E-081 | same environment limit | as above | PASS |
| DS-E2E-082 | no schema/row-count option | new read-only Sentinel menu option | PASS |
| DS-E2E-083 | Kafka CLI JVM exit 139 | runner executed from a file, not stdin; larger heap | PASS |

`docs/VALIDATION.md` for 4.2.1 recorded that no authenticated PostgreSQL or Kafka
session was ever performed, so these were newly-exercised areas rather than
regressions.

## Still deployed after this run

`--keep` left everything standing: the four E2E namespaces with their fixtures,
and the `cert-manager` namespace (3/3 controllers Ready, with
`Certificate/ds-e2e-managed` Ready=True and the controlled
`Certificate/ds-e2e-managed-failure` Ready=False). See `COMMANDS.md` for the
manual verification steps.

## Reproduce

```bash
bash devopssentinel-e2e/run-all.sh --mode FULL          # full suite
bash devopssentinel-e2e/run-all.sh --domain gitops      # one domain
bash devopssentinel-e2e/run-all.sh --failed             # rerun prior failures
KEEP_ON_FAILURE=1 bash devopssentinel-e2e/run-all.sh    # keep fixtures on failure
bash devopssentinel-e2e/cleanup.sh                      # remove fixtures only
```
