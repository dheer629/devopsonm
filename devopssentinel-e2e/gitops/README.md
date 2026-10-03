# Isolated local Flux fixtures

Run with `../run-all.sh --domain gitops` from this directory, or
`./devopssentinel-e2e/run-all.sh --domain gitops` from the repository root.
The shared preflight must confirm the disposable WSL cluster before deployment.

The fixtures live only in `devopssentinel-e2e-gitops`. Existing Flux controllers
reconcile new labelled resources; existing Flux objects are never edited.
There is no GitHub operation or external Git remote.

`local_git_server.py` creates a real local repository inside a pod's `emptyDir`,
serves Git's `http-backend`, and serves a small Helm chart on the same internal
Service. The server disables Git receive-pack. Its `/advance` endpoint creates
one more known fixture commit and is reached by the harness over a temporary
loopback-only Kubernetes port-forward. The Service has no ingress or NodePort.

| Case | Real condition compared with Sentinel |
| --- | --- |
| DS-E2E-060 | Suspended Kustomization |
| DS-E2E-061 | GitRepository fetch failure and actual controller message/transition |
| DS-E2E-062 | Ready GitRepository and artifact commit |
| DS-E2E-063 | Ready Kustomization and Git-deployed workload |
| DS-E2E-064 | Failed Kustomization from a missing repository path |
| DS-E2E-065 | Ready HelmRelease installing a Deployment and Service |
| DS-E2E-066 | Failed HelmRelease from an intentional chart rendering error |
| DS-E2E-067 | Git source, Kustomization inventory and HelmRelease graph |
| DS-E2E-068 | Second local commit, temporarily unapplied revision, recovery |
| DS-E2E-069 | Pod/ReplicaSet/Deployment/Helm/Kustomization/Git ownership chain |

The revision test suspends only `Kustomization/ds-e2e-ready`, commits to the
disposable local repository, and waits for normal Flux source polling. It
compares the observed source/applied revision difference, resumes that same
fixture in a `finally` block, and verifies the new workload revision. Controller
status is never fabricated or patched.

All waits and network requests have deadlines. The shared harness records the
generated manifests, real API objects, Sentinel output and expected-versus-actual
results in private evidence directories. Missing Flux prerequisites are reported
as `BLOCKED`; failed API/Sentinel comparisons are reported as `FAIL`.

The tools image is built and imported locally by the shared harness; it is never
pushed. Keep the namespace for investigation and use `../cleanup.sh` from this
directory when finished. Cleanup preserves reports and evidence.
