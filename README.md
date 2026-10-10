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

The interactive console requires a terminal. `--resources`, `--network`, `--storage`, `--triage-workload Deployment/NAME`, `--certificates`, `--cert-expiry`, `--doctor`, `--capabilities`, `--snapshot` and `--live-validate` support scripted reports. `--json` wraps report lines and their exit status in one JSON object. `--self-test`, `--explain` and `--ui-debug` produce plain text. `--components`, `--licenses`, `--offline-check`, `--verify` and `--checksum` report the bundled toolchain and need no cluster access.

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
python3 tests/e2e.py --context vcluster-docker_dev --namespace devopsonm --workload sentinel-platform
bash scripts/test-faults.sh vcluster-docker_dev
python3 tests/access_and_tui.py --context vcluster-docker_dev --namespace devopsonm
```

The E2E runner compares live pod names with the Kubernetes API, exercises report modes, JSON and error exits, and verifies evidence checksums, permissions and redaction. Fault testing temporarily creates a failed Pod, pending PVC, short-lived TLS certificate and canary Secret in `devopsonm`, then removes them. It refuses to overwrite existing fixtures. Access tests use Kubernetes impersonation (requires impersonation permission) to verify real RBAC denials and open pseudo-terminals to check dashboard startup and terminal restoration. Private outputs are written under `~/.devopssentinel/e2e-results/`; they are not committed. GitHub Actions runs offline and non-root container checks without cluster credentials.

See [the recorded validation results and coverage limits](docs/VALIDATION.md).

## Self-contained release

The engine resolves each critical tool through a bundled-toolchain registry. A
release build embeds validated binaries under `$HOME/.devopssentinel/bin` and the
engine prefers them, so startup needs no internet access, no package installation
and no sudo. Resolution is process-local: nothing is written to a shell profile
and no system binary is ever replaced.

```bash
bash DevOps_K8s_Sentinel_FINAL_GP.sh --components      # inventory + feature dependency matrix
bash DevOps_K8s_Sentinel_FINAL_GP.sh --licenses        # bundled component licenses
bash DevOps_K8s_Sentinel_FINAL_GP.sh --offline-check   # payload, binaries, checksums, platform
bash DevOps_K8s_Sentinel_FINAL_GP.sh --verify          # executable + extracted component digests
bash DevOps_K8s_Sentinel_FINAL_GP.sh --checksum        # SHA-256 digests
```

Set `DEVOPSSENTINEL_USE_SYSTEM_TOOLS=1` to prefer host tools instead. A component
whose digest does not match its manifest is reported `CORRUPT` and is never
executed; `--doctor` classifies every component as `BUNDLED`, `SYSTEM`,
`UNAVAILABLE`, `INCOMPATIBLE` or `CORRUPT`.

To build the single self-extracting artifact:

```bash
build/fetch-components.sh linux-amd64     # downloads + verifies upstream SHA-256
build/build-payload.sh linux-amd64
build/build-self-extracting.sh linux-amd64
build/test-bundle.sh                      # runs the real artifact under a minimal PATH
```

See [`build/README.md`](build/README.md) for the component pins and the release
gates.

## Cluster connections

The target cluster is a first-class, configurable object. Open **Settings → Cluster connection**.

* **Discovery** scans `$KUBECONFIG`, `~/.kube/*`, a mounted host directory (`/host-kube`,
  `/kubeconfig`), the WSL Windows tree (`/mnt/c/Users/*/.kube/config`) and the in-cluster service
  account. Every context in every file becomes a candidate.
* **Classification** labels each context from evidence — `DOCKER_DESKTOP`, `KIND`, `MINIKUBE`,
  `K3D`, `VCLUSTER`, `EKS`, `GKE`, `AKS`, `IN_CLUSTER`, `GENERIC` — never from a guess.
* **Test** probes one candidate and reports reachability, server version, namespace count and
  latency before you commit.
* **Auto-detect** probes every candidate and activates the first reachable one.
* **Activate** materialises an effective kubeconfig under the private state directory and points
  *both* `kubectl` and the Bash engine at it, so every page follows the same cluster.

Two fields make a container work against a cluster published on the Docker host:

* **API server override** — e.g. `https://host.docker.internal:11259` when the kubeconfig says
  `https://localhost:10093` (a dead `vcluster` port-forward).
* **Skip TLS verification** — required when the certificate name cannot match the override.

### Container

```bash
docker run -d --name devopssentinel-web --restart unless-stopped -p 127.0.0.1:8765:8765 \
  -v "$USERPROFILE/.kube:/host-kube:ro" devopssentinel-web:1.1.0
```

Mount a *directory* (`~/.kube`) rather than a single file: Docker creates a directory at the
mount point when the source is missing, and a mounted file that does not exist breaks the mount.

### Detected clusters — finding a WSL cluster from a container

A container cannot read the WSL filesystem or the host process list, so the WSL cluster is found
**by its published API port and proven with an unauthenticated `/version` call**. Two sources are
combined:

* the **Docker socket**, when mounted read-only: every container is inspected for a Kubernetes
  fingerprint (vcluster, kind, k3s, minikube, kube-apiserver, rancher) and its published host ports
  become candidate endpoints — so the UI can say *"`vcluster.cp.dev` (VCLUSTER) at
  `host.docker.internal:11259`"* rather than just an IP:port;
* a **port sweep** of well-known Kubernetes API ports (6443, 8443, 16443, 11259, …) across
  `host.docker.internal`, `gateway.docker.internal` and the container's own default gateway.

Every candidate is proven, never guessed. **Connect** then pairs a discovered endpoint with the
kubeconfig that actually authenticates against it and activates the result — one click from "scan"
to "live data".

```bash
docker run -d --name devopssentinel-web --restart unless-stopped \
  --group-add 0 \
  -p 127.0.0.1:8765:8765 \
  -v "$USERPROFILE/.kube:/host-kube:ro" \
  -v //var/run/docker.sock:/var/run/docker.sock:ro \
  devopssentinel-web:1.2.1
```

`--group-add 0` is required for the socket: it is `root:docker` mode `660`, and the app runs as an
unprivileged user. Without it the socket is mounted but unreadable, and the UI says so instead of
silently returning nothing. Use `--group-add $(stat -c %g /var/run/docker.sock)` on a Linux host
where the socket belongs to the `docker` group.

> Mounting the Docker socket grants the container control of the Docker daemon. DevOpsSentinel only
> ever issues read-only `GET /containers/json`, but the grant itself is broad — omit the socket mount
> if that trade-off is unacceptable; the port sweep still finds the endpoint.

Tune discovery with `DSWEB_HOST_ALIASES=host2,host3` (extra host names to sweep).

### Live data

The read-only SQL console and the Kafka topic lister are opt-in and can now be switched on from
Settings without recreating the container. Each still needs a reachable endpoint: a ClusterIP
Service (e.g. `ds-e2e-kafka:9092`) is only reachable inside the cluster, so use a NodePort, a
LoadBalancer or a port-forward, and enter that host and port in the page.

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
(`nodeAddress` on `/api/v1/system`), because the bundled platform PostgreSQL (`:30432`) and Kafka
(`:30092`) are NodePorts — they answer on a node, never on `127.0.0.1`.
`devopssentinel-web/scripts/live-smoke.sh` proves that path end to end and prints what was written and
what the API read back.

**PKI / TLS.** The PKI page has two tabs: **Certificates** (nearest-expiry order, with the real X.509
serial, SAN, issuer and source of each certificate) and **Secrets** — a Secret inventory that joins the
certificate expiry for every `kubernetes.io/tls` Secret, so secret rotation and certificate validity are
visible in one place. `GET /api/v1/secrets` returns metadata only; Secret data and private keys are
never requested or transported.

