# DevOpsSentinel E2E — Manual Command List

Copy-paste, in order, from a **WSL (Ubuntu) shell**. Every step is read-only on the
cluster except the ones explicitly marked **DEPLOY / INSTALL**. Nothing in this list
deletes fixtures — the environment is left standing for inspection.

```bash
ROOT='/mnt/c/Users/dheer/OneDrive/Desktop/AI Projects/DeVops_latest'
cd "$ROOT"
```

---

## STEP 1 — Confirm the disposable local cluster (safety gate)

```bash
kubectl config current-context                      # expect: vcluster-docker_dev
kubectl cluster-info
kubectl get nodes -o wide                           # expect: single node "dev"
docker ps --filter name=vcluster.cp.dev --format '{{.Names}} {{.Status}}'
```

STOP if the context is not your local WSL/vcluster test cluster.

## STEP 2 — INSTALL pinned cert-manager (unblocks DS-E2E-059, DS-E2E-156)

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager           --timeout=300s
kubectl -n cert-manager rollout status deploy/cert-manager-cainjector --timeout=300s
kubectl -n cert-manager rollout status deploy/cert-manager-webhook    --timeout=300s
kubectl wait --for=condition=Established crd/certificates.cert-manager.io --timeout=180s
kubectl get crd | grep cert-manager
```

The harness does the same thing with `--install-prereqs` (see STEP 5).

## STEP 3 — DEPLOY the E2E tools image

```bash
docker build -t ds-e2e-tools:local -f devopssentinel-e2e/Dockerfile .
docker save ds-e2e-tools:local | docker exec -i vcluster.cp.dev ctr -n k8s.io images import -
docker exec vcluster.cp.dev ctr -n k8s.io images ls | grep ds-e2e-tools
```

The image carries `git-daemon` (for `git-http-backend`), `python3`, `git` and
`postgresql-client`.

## STEP 4 — DEPLOY the E2E namespaces

```bash
for ns in devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f -
done
```

## STEP 5 — DEPLOY every fixture, run the full suite, keep everything

```bash
bash devopssentinel-e2e/run-all.sh --mode FULL --install-prereqs --keep
```

* `--install-prereqs` installs pinned cert-manager if the CRDs are missing.
* `--keep` leaves all fixtures in place (no cleanup).
* Targeted re-runs:
  ```bash
  bash devopssentinel-e2e/run-all.sh --domain certificates --keep
  bash devopssentinel-e2e/run-all.sh --domain database     --keep
  bash devopssentinel-e2e/run-all.sh --test DS-E2E-082 --keep
  ```

## STEP 6 — Verify each previously blocked case by hand

### DS-E2E-059 / DS-E2E-156 — cert-manager issuance (real X.509 from the controller)

```bash
kubectl -n devopssentinel-e2e-pki get issuer,clusterissuer
kubectl -n devopssentinel-e2e-pki get certificate -o wide
kubectl -n devopssentinel-e2e-pki get certificaterequest
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-managed -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
# Sentinel view (Certificate Ready + issuer relationship):
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev \
  --namespace devopssentinel-e2e-pki --certificates --no-color
```

### DS-E2E-080 / DS-E2E-081 — PostgreSQL in-cluster client (Docker-network workaround)

```bash
kubectl -n devopssentinel-e2e get pod ds-e2e-postgres ds-e2e-pg-client
kubectl -n devopssentinel-e2e exec ds-e2e-pg-client -- \
  bash /workspace/tests/postgres_integration.sh \
  ds-e2e-postgres.devopssentinel-e2e.svc 5432 devopssentinel sentinel_integration \
  /run/credentials/password
```

Expect `PostgreSQL integration: NN checks, result=PASS`.

### DS-E2E-082 — schema / row-count read-only option (new Sentinel menu entry)

```bash
# Interactive: open the Sentinel inside the client pod and use menu 22
kubectl -n devopssentinel-e2e exec -it ds-e2e-pg-client -- bash
#   bash /workspace/DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev \
#     --namespace devopssentinel-e2e --output /tmp/sntl
#   Menu: 22 PostgreSQL -> Explicit read-only session -> host/port/db/user -> password
#   -> "Schema / row counts"   (expect: public | e2e_audit | 3)
```

The integration script (STEP above) exercises the same option non-interactively and
asserts the table name and the exact row count.

### DS-E2E-083 — Kafka broker, topic, messages, consumer group

```bash
kubectl -n devopssentinel-e2e get pod ds-e2e-kafka
kubectl -n devopssentinel-e2e exec ds-e2e-kafka -- bash -c '
  source /fixture/sentinel.sh
  export PATH=/opt/kafka/bin:$PATH KAFKA_HEAP_OPTS="-Xms128m -Xmx384m"
  API_TIMEOUT=30
  kafka_connectivity_report ds-e2e-kafka.devopssentinel-e2e.svc:9092
  kafka_topics_report     ds-e2e-kafka.devopssentinel-e2e.svc:9092
  kafka_groups_report     ds-e2e-kafka.devopssentinel-e2e.svc:9092'
```

> **Important:** run the Sentinel from a **file** or with `bash -c`, not by piping the
> script on stdin. The Sentinel's `run_bounded` duplicates stdin for its children;
> piping with `bash -s` corrupts the script stream and every bounded child exits 139.

## STEP 7 — Read the evidence

```bash
ls -1dt ~/.devopssentinel/real-e2e/*/ | head -1                 # newest run
cat "$(ls -1dt ~/.devopssentinel/real-e2e/*/ | head -1)DS-E2E-082/result.json"
cat devopssentinel-e2e/reports/DEVOPSSENTINEL_E2E_REPORT.md     # published report
```

## STEP 8 — Inspect what is still deployed

```bash
kubectl get ns | grep -E 'devopssentinel|cert-manager'
for ns in devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki; do
  echo "== $ns =="; kubectl -n "$ns" get all
done
```

## STEP 9 — Cleanup (OPTIONAL, only when you are finished)

```bash
bash devopssentinel-e2e/cleanup.sh            # deletes only the 4 E2E namespaces
kubectl delete namespace cert-manager         # only if you no longer need cert-manager
```

Never run `kubectl delete namespace --all` or wildcard deletes.

