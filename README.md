# DevOpsSentinel

Single-file, read-only Kubernetes, Flux, Helm, PKI/TLS and platform operations console. Version **4.2.1** fixes normal-user cache access, misleading validation results, pending-PVC visibility and evidence formatting, and restores five omitted fixture suites.

## Run locally in WSL

Requires Bash 4.4+, `kubectl`, `jq`, `openssl`, GNU coreutils and an awk implementation supporting dynamic field widths (GNU awk is included in the container). `helm`, `flux`, database/Kafka clients and metrics/cert-manager APIs enable optional features. Run as your normal Linux user. Runtime files remain private beneath Linux `$HOME`, not the Windows workspace.

```bash
bash DevOps_K8s_Sentinel_FINAL_GP.sh --help
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopsonm
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopsonm --triage
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace flux-system --gitops --json
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopsonm --evidence INCIDENT-123
```

The interactive console requires a terminal. `--resources`, `--network`, `--storage`, `--triage-workload Deployment/NAME`, `--certificates`, `--cert-expiry`, `--doctor`, `--capabilities`, `--snapshot` and `--live-validate` support scripted reports. `--json` wraps report lines and their exit status in one JSON object. `--self-test`, `--explain` and `--ui-debug` produce plain text.

The utility performs no Kubernetes mutation, Git publishing or Flux reconciliation. Its separate deployment/test scripts perform explicitly scoped setup operations. Report data is sequential and may be incomplete. Exit codes are `0` for successful collection/no failing findings, `1` for failing findings, `2` for invalid input/configuration, `3` for bootstrap API/authentication failure, and `4` for unavailable required data. Optional APIs absent from live validation are marked `OPTIONAL_UNAVAILABLE`. A successful collector does not imply healthy workloads.

## Existing WSL cluster and Flux deployment

This local overlay uses the existing `vcluster-docker_dev` context, Docker node container `vcluster.cp.dev`, and installed Flux controllers. It does not install or replace the cluster or Flux. GitHub authentication uses the existing Windows Git credential manager; `gh auth login` is not required for `git push`.

```powershell
git add .gitattributes .gitignore .dockerignore Dockerfile DevOps_K8s_Sentinel_FINAL_GP.sh README.md deploy scripts tests docs .github
git commit -m "Validate and deploy DevOpsSentinel"
git push -u origin main
wsl -d Ubuntu -- bash scripts/deploy-wsl.sh
```

The deployment script builds and self-tests a non-root image, imports it into the WSL node, applies the Flux source/sync objects, reconciles the pushed `main` revision, and runs one validation Job. Flux deploys a small Redis reference workload and an hourly read-only validation CronJob in `devopsonm`. The image has `imagePullPolicy: Never`: this overlay is for this local cluster, and the image must be rebuilt/imported after script changes. Other clusters need a reachable image registry and an appropriate kubectl version (`KUBECTL_VERSION` build argument).

The CronJob's kubeconfig contains only API, CA-file and projected token-file references; it contains no credentials. Its service account has namespace get/list permissions and limited cluster reads. Secret list permission is needed for TLS inspection and grants API access to full Secret objects; the utility projects certificate metadata and never exports Secret payloads or private keys. Restrict this role to namespaces where that permission is appropriate.

The existing source-controller trusts the workstation's TLS inspection CA through its existing CA mount; no credentials or workstation certificates are stored here. On this machine, external DNS forwarding failed while internal service DNS worked. CoreDNS was repaired to use reachable upstreams; the prior configuration is saved privately at `/home/dheer/.devopssentinel/devopsonm-dns-backup.json`. This environment repair is not part of the application manifests.

## Validation

```bash
bash DevOps_K8s_Sentinel_FINAL_GP.sh --self-test --no-color
bash tests/regression.sh
python3 tests/e2e.py --context vcluster-docker_dev --namespace devopsonm --workload sentinel-demo
bash scripts/test-faults.sh vcluster-docker_dev
python3 tests/access_and_tui.py --context vcluster-docker_dev --namespace devopsonm
```

The E2E runner compares live pod names with the Kubernetes API, exercises report modes, JSON and error exits, and verifies evidence checksums, permissions and redaction. Fault testing temporarily creates a failed Pod, pending PVC, short-lived TLS certificate and canary Secret in `devopsonm`, then removes them. It refuses to overwrite existing fixtures. Access tests use Kubernetes impersonation (requires impersonation permission) to verify real RBAC denials and open pseudo-terminals to check dashboard startup and terminal restoration. Private outputs are written under `~/.devopssentinel/e2e-results/`; they are not committed. GitHub Actions runs offline and non-root container checks without cluster credentials.

See [the recorded validation results and coverage limits](docs/VALIDATION.md).

## Browser edition — DevOpsSentinel Web

`devopssentinel-web/` contains a local, read-only browser control center that drives this same
engine through a typed FastAPI adapter (no ANSI scraping, no duplicated Kubernetes logic, no
cluster mutation).

```bash
cd devopssentinel-web
./devopssentinel-web --open        # http://127.0.0.1:8765
```

It exposes the engine's report modes as typed operations, adds a problem-first dashboard, findings
queue, pod/log/event investigation, dependency topology, GitOps and PKI dashboards, network and
storage centers, incident evidence browsing and local exports. The complete per-feature accounting
lives in [`devopssentinel-web/docs/FEATURE_PARITY_MATRIX.md`](devopssentinel-web/docs/FEATURE_PARITY_MATRIX.md).

**Interface.** Eight themes ship in the picker; `Kubernetes` reproduces the Kubernetes Dashboard
layout — an indigo breadcrumb band, a sectioned sidebar with an inline namespace picker, flat white
cards and sortable tables with inline usage bars. The default follows the OS colour scheme. Live
CPU/memory usage comes from two read-only `kubectl top` calls (`/api/v1/metrics/nodes`,
`/api/v1/metrics/pods`); without metrics-server the pages say so instead of failing. See
[`devopssentinel-web/docs/SECURITY.md`](devopssentinel-web/docs/SECURITY.md).

**Live refresh.** The `LIVE` selector in the top bar re-reads every cluster-facing query on the chosen
interval (5–60 s) and stops while the tab is hidden; **Refresh now** forces one immediately. The opt-in
read-only SQL console and Kafka topic lister prefill the node address the backend reports
(`nodeAddress` on `/api/v1/system`), because the bundled demo PostgreSQL (`:30432`) and Kafka
(`:30092`) are NodePorts — they answer on a node, never on `127.0.0.1`.
`devopssentinel-web/scripts/live-smoke.sh` proves that path end to end and prints what was written and
what the API read back.

