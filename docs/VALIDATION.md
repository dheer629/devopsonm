# WSL Kubernetes validation — 3 October 2026

DevOpsSentinel 4.2.1 was executed as a normal WSL user, in pseudo-terminals, and as UID 10001 in Kubernetes. The target was the existing Ubuntu WSL context `vcluster-docker_dev`, Kubernetes **v1.30.4**, node `dev`. No replacement cluster was created.

Tested utility SHA-256: `3b610cbea4158c7b9ada6c677fa30ef6141b87d32b2a26d71ad77d65ca6f1420`.

## Results

| Check | Result |
| --- | --- |
| Built-in offline suites | **21/21 passed**, including **60/60** Splunk response assertions |
| Targeted cache, collector, PVC, dependency and scope regressions | **23/23 passed** |
| Existing `learnalgorithm` namespace E2E | **36/36 passed** |
| Dedicated `devopsonm` namespace E2E after fixes | **37/37 passed** |
| Failed Pod, pending PVC, short-lived TLS certificate and canary Secret | **40/40 passed**; fixtures removed |
| Real API RBAC denials and PTY dashboard navigation/restoration | **8/8 passed** |
| Bash syntax; ShellCheck error severity | Passed |
| Non-root Alpine container self-tests | **21/21 passed** |
| Flux source and Kustomization | Ready; matching pushed Git revision |
| In-cluster validation Job | Completed; JSON `exit_status: 0` |
| Reference Redis workload | Deployment available; `redis-cli ping` returned `PONG` |
| Reader service account | Can list namespace Pods; cannot create Pods |
| GitHub Actions, initial deployment commit | [Passed](https://github.com/dheer629/devopsonm/actions/runs/37124504377) |

The healthy E2E run compares actual API Pod names, covers all 17 report modes plus workload/dependency reports, validates JSON/exit codes and bad-input handling, and verifies evidence checksums, file permissions and absence of the canary Secret/private keys. PTY tests open the Pod grid, switch to detail, return to the dashboard and quit at widths 80 and 120. They verify terminal attributes are restored. API-denial tests impersonate an unprivileged identity for `--doctor`, `--live-validate`, `--triage` and `--health`; each returns exit 4.

Private raw results remain under the WSL home directory:

- Baseline: `~/.devopssentinel/e2e-results/20261003T125123Z/summary.json`
- Failure scenarios: `~/.devopssentinel/e2e-results/20261003T130045Z/summary.json`
- Final healthy namespace: `~/.devopssentinel/e2e-results/20261003T130221Z/summary.json`

The failure run preceded addition of the explicit Deployment-to-Service assertion to the runner. That relationship passed the final healthy run and the deterministic dependency regressions. The same corrected utility source was used for both runs.

## Defects fixed

1. Startup applied `chmod 600` to the cache directory, removing directory search permission. Collectors could not write as a normal user. Permissions now distinguish files (600) and directories (700), and self-tests perform a real cache write.
2. `--live-validate` trusted collector wrapper exit codes even though wrappers deliberately tolerate failures. It now checks each persisted collector status, labels absent optional APIs, and returns 4 for unavailable required data.
3. `--doctor` and `--health` returned success with unavailable scope or denied Pod inventory. These conditions now return 4. Invalid explicit namespaces are also rejected when enumeration is allowed.
4. Storage dependencies discarded pending PVCs when the PV join had no match. They now show `UNBOUND` and retain the claim.
5. Evidence findings used escaped separators and could collapse into an empty JSON array. Findings now preserve the tab-separated rows as structured JSON.
6. Dependency queries passed a null owner kind to `ascii_downcase`, raising a jq error for standalone Pods. Null owners are handled, ReplicaSet/Job owner chains resolve their parent workload, Deployment-to-Service correlation follows those chains, and parser failures propagate.
7. JSON-emitter errors were hidden by the report exit code. Emit failures now propagate.
8. Certificate summaries appended a second zero when grep found no matches. Empty counts now remain single numeric values.
9. Five integration suites were omitted from the public self-test. They are now included; the GitOps certificate fixture uses the correct critical-expiry interval, and the Splunk assertion helper is self-contained.
10. Alpine's minimal awk did not support the renderer's dynamic widths. The container now includes GNU awk and passes the same fixtures as WSL.

## GitHub and Flux setup

Relevant prior conversation context was recovered from the local June deployment history. The existing Windows Git credential manager successfully pushed `main` despite `gh` being logged out. The previously installed source-controller CA mount was reused; TLS verification remained enabled. No token, kubeconfig credential, TLS private key or workstation CA was committed.

CoreDNS resolved internal services but external names failed through its inherited resolver. A direct query to `1.1.1.1` succeeded. The Corefile forwarding line was changed to `forward . 1.1.1.1 8.8.8.8`, after saving the original at `/home/dheer/.devopssentinel/devopsonm-dns-backup.json`. GitHub then resolved and both Git sources became Ready. The existing `learnalgorithm` application remained deployed.

To restore the original local CoreDNS configuration if needed:

```bash
kubectl --context vcluster-docker_dev -n kube-system patch configmap coredns \
  --type=merge --patch-file "$HOME/.devopssentinel/devopsonm-dns-backup.json"
```

The repository's Flux objects are `flux-system/GitRepository/devopsonm` and `flux-system/Kustomization/devopsonm`, tracking `main` at `./deploy/local`. The deployment script verifies source reconciliation, manifest reconciliation, workload rollout and one validation Job. The local image must be rebuilt/imported after utility changes; this is not a registry publishing pipeline.

## Coverage limits

Metrics-server and cert-manager are absent on this cluster, so their absence paths were exercised live and their parsing logic was covered by fixtures. No live Kafka, Splunk or authenticated PostgreSQL diagnostic session was performed; discovery and applicable offline fixtures were tested. No HelmRelease exists here. Certificate metadata/expiry were tested with a generated TLS Secret; arbitrary external TLS endpoints and every interactive menu permutation were not exercised. ShellCheck was run at error severity, not as a warning-free certification. These results establish the tested local behavior, not universal production readiness.

Relevant upstream references: [Flux GitRepository reconciliation](https://fluxcd.io/flux/components/source/gitrepositories/) and [Kubernetes DNS diagnosis](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/).
