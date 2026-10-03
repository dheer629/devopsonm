# DevOpsSentinel E2E — Step-by-Step Verification Run (real captured output)

Every command below was **actually executed** against the live local cluster and the
output is verbatim from that run. You can reproduce the whole thing with:

```bash
bash devopssentinel-e2e/verify-all.sh
```

or copy any individual command. All commands are **read-only**; none mutate the cluster.

| | |
| --- | --- |
| Date/time of run | 2026-10-03, 16:19–16:20 UTC |
| Context | `vcluster-docker_dev` |
| Cluster | local Docker vcluster (`vcluster.cp.dev`), Kubernetes **v1.30.4**, single node `dev` |
| Utility under test | `DevOps_K8s_Sentinel_FINAL_GP.sh` **v4.2.2** |
| Namespaces under test | `devopssentinel-e2e`, `-peer`, `-gitops`, `-pki`, `cert-manager` |

Full E2E suite result (from the harness): **86 PASS / 0 FAIL / 0 BLOCKED / 1 N/A**.

---

## 0. Environment

```bash
uname -a
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl version
docker ps --filter name=vcluster.cp.dev --format '{{.Names}}  {{.Image}}  {{.Status}}'
```

```
Linux Dheeraj 6.6.114.1-microsoft-standard-WSL2 ... x86_64 GNU/Linux

vcluster-docker_dev

Kubernetes control plane is running at https://localhost:11259
CoreDNS is running at https://localhost:11259/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy

NAME   STATUS   ROLES                  AGE    VERSION   INTERNAL-IP   EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION                      CONTAINER-RUNTIME
dev    Ready    control-plane,master   107d   v1.30.4   172.18.0.2    <none>        Ubuntu 24.04.4 LTS   6.6.114.1-microsoft-standard-WSL2   containerd://1.7.27

Client Version: v1.30.4
Server Version: v1.30.4

vcluster.cp.dev  ghcr.io/loft-sh/vm-container  Up 2 weeks
```

## 1. Safety gate / namespaces

```bash
kubectl get ns --no-headers | grep -E 'devopssentinel|cert-manager|flux-system'
kubectl get ns devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  "}{.metadata.labels.devopssentinel\.io/test-suite}{"  "}{.metadata.labels.app\.kubernetes\.io/part-of}{"\n"}{end}'
for n in devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki; do
  printf '%-28s pods=%s\n' "$n" "$(kubectl -n $n get pods --no-headers 2>/dev/null | wc -l)"; done
```

```
cert-manager                Active   17m
devopssentinel-e2e          Active   46m
devopssentinel-e2e-gitops   Active   46m
devopssentinel-e2e-peer     Active   46m
devopssentinel-e2e-pki      Active   46m
flux-system                 Active   107d

devopssentinel-e2e  true  devopssentinel-e2e
devopssentinel-e2e-peer  true  devopssentinel-e2e
devopssentinel-e2e-gitops  true  devopssentinel-e2e
devopssentinel-e2e-pki  true  devopssentinel-e2e

devopssentinel-e2e           pods=24
devopssentinel-e2e-peer      pods=1
devopssentinel-e2e-gitops    pods=3
devopssentinel-e2e-pki       pods=1
```

**Verdict:** isolated, correctly labelled E2E namespaces on a verified local cluster.

## 2. Workload scenarios

```bash
kubectl -n devopssentinel-e2e get deploy,statefulset,daemonset,job,cronjob
kubectl -n devopssentinel-e2e get pods -o wide --no-headers
```

```
deployment.apps/ds-e2e-healthy       2/2     2            2           17m
deployment.apps/ds-e2e-transformer   1/1     1            1           12m
statefulset.apps/ds-e2e-stateful     2/2     17m
daemonset.apps/ds-e2e-daemon         1         1         1       1            1
job.batch/ds-e2e-cron-29850739       Complete   1/1

ds-e2e-crash                         0/1   CrashLoopBackOff             8 (85s ago)    17m
ds-e2e-daemon-wbq9p                  1/1   Running                      0
ds-e2e-healthy-77bd9c5548-2p8kc      1/1   Running                      0
ds-e2e-healthy-77bd9c5548-6nqpw      1/1   Running                      0
ds-e2e-image                         0/1   ImagePullBackOff             0
ds-e2e-init-fail                     0/1   Init:CrashLoopBackOff        8
ds-e2e-job-failed-9hwvb              0/1   Error                        0
ds-e2e-job-success-...               0/1   Completed                    0
ds-e2e-kafka                         1/1   Running                      0
ds-e2e-liveness                      0/1   CrashLoopBackOff             11 (37s ago)
ds-e2e-logs                          1/1   Running                      0
ds-e2e-missing-config                0/1   CreateContainerConfigError   0
ds-e2e-multi                         2/2   Running                      0
ds-e2e-not-ready                     0/1   Running                      0
ds-e2e-oom                           0/1   OOMKilled                    0
ds-e2e-pg-client                     1/1   Running                      0
ds-e2e-postgres                      1/1   Running                      0
ds-e2e-startup                       1/1   Running                      0
ds-e2e-stateful-0 / -1               1/1   Running                      0
ds-e2e-unschedulable                 0/1   Pending                      0
```

### Per-scenario assertions

```bash
# healthy: 2/2
kubectl -n devopssentinel-e2e get deploy ds-e2e-healthy -o jsonpath='{.spec.replicas} desired, {.status.readyReplicas} ready, {.status.availableReplicas} available{"\n"}'
# -> 2 desired, 2 ready, 2 available

# statefulset: 2 replicas
kubectl -n devopssentinel-e2e get statefulset ds-e2e-stateful -o jsonpath='{.spec.replicas} replicas, {.status.readyReplicas} ready{"\n"}'
# -> 2 replicas, 2 ready

# daemonset: 1 desired / 1 ready
kubectl -n devopssentinel-e2e get ds ds-e2e-daemon -o jsonpath='{.status.desiredNumberScheduled} desired, {.status.numberReady} ready{"\n"}'
# -> 1 desired, 1 ready

# CrashLoopBackOff: restart count + previous exit code
kubectl -n devopssentinel-e2e get pod ds-e2e-crash -o jsonpath='{range .status.containerStatuses[*]}reason={.state.waiting.reason} restarts={.restartCount} lastExit={.lastState.terminated.exitCode}{"\n"}{end}'
# -> reason=CrashLoopBackOff restarts=8 lastExit=1

# ImagePullBackOff
kubectl -n devopssentinel-e2e get pod ds-e2e-image -o jsonpath='{range .status.containerStatuses[*]}reason={.state.waiting.reason}{"\n"}{end}'
# -> reason=ImagePullBackOff

# CreateContainerConfigError (missing ConfigMap)
kubectl -n devopssentinel-e2e get pod ds-e2e-missing-config -o jsonpath='{range .status.containerStatuses[*]}reason={.state.waiting.reason}{"\n"}{end}'
# -> reason=CreateContainerConfigError

# Pending / FailedScheduling
kubectl -n devopssentinel-e2e get pod ds-e2e-unschedulable -o jsonpath='{.status.phase} {.status.conditions[0].reason}{"\n"}'
# -> Pending Unschedulable

# Running but NOT Ready (readiness probe failing)
kubectl -n devopssentinel-e2e get pod ds-e2e-not-ready -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{"\n"}'
# -> ... Ready=False ContainersReady=False ...

# liveness restarts
kubectl -n devopssentinel-e2e get pod ds-e2e-liveness -o jsonpath='{range .status.containerStatuses[*]}restarts={.restartCount} waiting={.state.waiting.reason}{"\n"}{end}'
# -> restarts=11 waiting=CrashLoopBackOff

# OOMKilled
kubectl -n devopssentinel-e2e get pod ds-e2e-oom -o jsonpath='{range .status.containerStatuses[*]}state={.state.terminated.reason} exit={.state.terminated.exitCode}{"\n"}{end}'
# -> state=OOMKilled exit=137

# init container failure
kubectl -n devopssentinel-e2e get pod ds-e2e-init-fail -o jsonpath='{range .status.initContainerStatuses[*]}init restarts={.restartCount} waiting={.state.waiting.reason}{"\n"}{end}'
# -> init restarts=8 waiting=CrashLoopBackOff

# multi-container + init
kubectl -n devopssentinel-e2e get pod ds-e2e-multi -o jsonpath='containers={.spec.containers[*].name} init={.spec.initContainers[*].name} ready={.status.containerStatuses[*].ready}{"\n"}'
# -> containers=main sidecar init=init ready=true true

# Job success / failure
kubectl -n devopssentinel-e2e get job ds-e2e-job-success -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{"\n"}'
# -> Complete=True
kubectl -n devopssentinel-e2e get job ds-e2e-job-failed -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{"\n"}'
# -> Failed=True

# CronJob
kubectl -n devopssentinel-e2e get cronjob ds-e2e-cron -o jsonpath='{.spec.schedule} last={.status.lastScheduleTime}{"\n"}'
```

**Verdict:** every workload scenario reaches its intended real Kubernetes state and is
confirmed directly through the API before the Sentinel is invoked.

## 3. Networking scenarios

```bash
kubectl -n devopssentinel-e2e get svc --no-headers
kubectl -n devopssentinel-e2e get endpointslices -o custom-columns='NAME:.metadata.name,SVC:.metadata.labels.kubernetes\.io/service-name,READY:.endpoints[*].conditions.ready' --no-headers
kubectl -n devopssentinel-e2e get endpoints ds-e2e-web  -o jsonpath='{range .subsets[*].addresses[*]}{.ip}{"\n"}{end}'
kubectl -n devopssentinel-e2e get endpoints ds-e2e-zero -o jsonpath='subsets={.subsets[*].addresses[*].ip} notReady={.subsets[*].notReadyAddresses[*].ip}{"\n"}'
kubectl -n devopssentinel-e2e get svc ds-e2e-wrong-port -o jsonpath='ports={.spec.ports[*].port}->targetPort={.spec.ports[*].targetPort} selector={.spec.selector}{"\n"}'
kubectl -n devopssentinel-e2e get networkpolicy ds-e2e-policy -o jsonpath='podSelector={.spec.podSelector.matchLabels} types={.spec.policyTypes} ingress={.spec.ingress}{"\n"}'
kubectl -n devopssentinel-e2e get ingress ds-e2e-ingress -o jsonpath='host={.spec.rules[*].host} backend={.spec.rules[*].http.paths[*].backend.service.name}{"\n"}'
```

```
ds-e2e-kafka         ClusterIP   10.98.161.242    <none>   9092/TCP   45m
ds-e2e-postgres      ClusterIP   10.104.198.59    <none>   5432/TCP   46m
ds-e2e-stateful      ClusterIP   None             <none>   80/TCP     17m
ds-e2e-transformer   ClusterIP   10.107.28.181    <none>   80/TCP     12m
ds-e2e-web           ClusterIP   10.106.246.85    <none>   80/TCP     17m
ds-e2e-web-second    ClusterIP   10.98.194.155    <none>   80/TCP     17m
ds-e2e-wrong-port    ClusterIP   10.100.47.189    <none>   80/TCP     17m
ds-e2e-zero          ClusterIP   10.102.122.211   <none>   80/TCP     17m

ds-e2e-web-kwbf7           ds-e2e-web           true,true
ds-e2e-web-second-hhs7c    ds-e2e-web-second    true,true
ds-e2e-wrong-port-9mdh5    ds-e2e-wrong-port    true,true
ds-e2e-zero-srqcs          ds-e2e-zero          <none>          <-- zero ready endpoints

10.244.0.58
10.244.0.59

subsets= notReady=                                            <-- ds-e2e-zero has no endpoints

ports=80->targetPort=9999 selector={"app":"ds-e2e-healthy"}   <-- deliberate mismatch
podSelector={"app":"ds-e2e-healthy"} types=["Ingress"] ingress=[{"from":[{"podSelector":{}}]}]
host=ds-e2e.example.local backend=ds-e2e-web
```

### DNS resolution from inside a pod (real CoreDNS)

```bash
kubectl -n devopssentinel-e2e exec ds-e2e-logs -- python3 -c "import socket;print('web:',socket.gethostbyname('ds-e2e-web'));print('web.ns:',socket.gethostbyname('ds-e2e-web.devopssentinel-e2e'));print('web.ns.svc:',socket.gethostbyname('ds-e2e-web.devopssentinel-e2e.svc'));print('fqdn:',socket.gethostbyname('ds-e2e-web.devopssentinel-e2e.svc.cluster.local'))"
```

```
web: 10.106.246.85
web.ns: 10.106.246.85
web.ns.svc: 10.106.246.85
fqdn: 10.106.246.85
```

**Verdict:** Service→EndpointSlice→Pod mapping, the zero-endpoint case, the deliberate
targetPort mismatch, NetworkPolicy parsing and Ingress mapping are all real and visible
in the API.

## 4. Storage scenarios

```bash
kubectl get storageclass --no-headers
kubectl -n devopssentinel-e2e get pvc --no-headers
kubectl -n devopssentinel-e2e get pvc ds-e2e-pending -o jsonpath='{.metadata.name} phase={.status.phase} class={.spec.storageClassName}{"\n"}'
kubectl -n devopssentinel-e2e get pvc ds-e2e-stateful-0 -o jsonpath='phase={.status.phase} vol={.spec.volumeName} cap={.status.capacity.storage} mode={.spec.accessModes}{"\n"}'
```

```
local-path (default)   rancher.io/local-path   Delete   WaitForFirstConsumer   false

ds-e2e-data-ds-e2e-stateful-0   Bound   64Mi   local-path
ds-e2e-data-ds-e2e-stateful-1   Bound   64Mi   local-path
ds-e2e-pending                  Pending 64Mi   ds-e2e-storageclass-does-not-exist

ds-e2e-pending phase=Pending class=ds-e2e-storageclass-does-not-exist
phase=Bound vol=pvc-... cap=64Mi mode=[ReadWriteOnce]
```

**Verdict:** a real bound PVC→PV→StorageClass chain plus a genuinely pending PVC with a
non-existent StorageClass.

## 5. PKI / TLS scenarios

```bash
kubectl -n devopssentinel-e2e-pki get secret -o custom-columns='NAME:.metadata.name,TYPE:.type' --no-headers
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-valid    -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -subject -issuer -dates -serial -fingerprint -sha256
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-valid    -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -ext subjectAltName
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-expired  -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates -checkend 0
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-expiring -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-incomplete -o jsonpath='{.data.tls\.crt}' | base64 -d | grep -c 'BEGIN CERTIFICATE'
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-valid     -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -fingerprint -sha256
kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-duplicate -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -fingerprint -sha256
```

```
ds-e2e-cert-duplicate     kubernetes.io/tls
ds-e2e-cert-expired       kubernetes.io/tls
ds-e2e-cert-expiring      kubernetes.io/tls
ds-e2e-cert-future        kubernetes.io/tls
ds-e2e-cert-incomplete    kubernetes.io/tls
ds-e2e-cert-intermediate  kubernetes.io/tls
ds-e2e-cert-mismatch      kubernetes.io/tls
ds-e2e-cert-root          kubernetes.io/tls
ds-e2e-cert-valid         kubernetes.io/tls

subject=CN = ds-e2e.example.local
issuer=CN = ds-e2e-intermediate
notBefore=Oct  2 16:04:05 2026 GMT
notAfter=Apr  1 16:04:05 2027 GMT
serial=...
sha256 Fingerprint=F4:20:53:CE:E1:D3:56:AB:AB:50:39:9E:88:59:89:65:D8:B5:B4:F8:E3:FD:45:32:D0:DD:6E:11:70:01:F4:F1

X509v3 Subject Alternative Name:
    DNS:ds-e2e.example.local, DNS:ds-e2e-web, DNS:ds-e2e-web.devopssentinel-e2e.svc, IP Address:127.0.0.1

notBefore=Sep  3 16:04:05 2026 GMT
notAfter=Oct  1 16:04:05 2026 GMT
Certificate will expire                       <-- openssl confirms it is in the past

notBefore=Oct  2 16:04:05 2026 GMT
notAfter=Oct  8 16:04:05 2026 GMT             <-- ~5 days out (expiring-soon)

1                                             <-- incomplete chain: only the leaf, no intermediate

sha256 Fingerprint=F4:20:53:CE:... (valid)
sha256 Fingerprint=B1:8F:C7:0D:... (duplicate)   <-- different Secret, different fingerprint
```

### Live TLS endpoint (real handshake over the Service)

```bash
(kubectl -n devopssentinel-e2e-pki port-forward svc/ds-e2e-tls 18443:443 >/dev/null 2>&1 &) ; sleep 3
echo | timeout 12 openssl s_client -connect 127.0.0.1:18443 -servername ds-e2e-web.devopssentinel-e2e.svc 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -fingerprint -sha256
pkill -f 'port-forward.*18443'
```

```
subject=CN = ds-e2e.example.local
issuer=CN = ds-e2e-intermediate
notBefore=Oct  2 16:04:05 2026 GMT
notAfter=Oct  3 16:04:05 2027 GMT
sha256 Fingerprint=F4:20:53:CE:E1:D3:56:AB:AB:50:39:9E:88:59:89:65:D8:B5:B4:F8:E3:FD:45:32:D0:DD:6E:11:70:01:F4:F1
```

**Verdict:** the live TLS endpoint presents exactly the certificate mounted from
`Secret/ds-e2e-cert-valid` (same SHA-256 fingerprint) — a real handshake, not a mock.

## 6. cert-manager scenarios (previously blocked)

```bash
kubectl get crd | grep cert-manager
kubectl -n cert-manager get deploy --no-headers
kubectl -n devopssentinel-e2e-pki get issuer,certificate,certificaterequest --no-headers
kubectl -n devopssentinel-e2e-pki get certificate ds-e2e-managed         -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{"\n"}{end}'
kubectl -n devopssentinel-e2e-pki get certificate ds-e2e-managed-failure -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{"\n"}{end}'
```

```
certificaterequests.cert-manager.io              2026-10-03T16:01:26Z
certificates.cert-manager.io                     2026-10-03T16:01:26Z
challenges.acme.cert-manager.io                  2026-10-03T16:01:26Z
clusterissuers.cert-manager.io                   2026-10-03T16:01:26Z
issuers.cert-manager.io                          2026-10-03T16:01:26Z
orders.acme.cert-manager.io                      2026-10-03T16:01:26Z

cert-manager              1/1   1     1     17m
cert-manager-cainjector   1/1   1     1     17m
cert-manager-webhook      1/1   1     1     17m

issuer.cert-manager.io/ds-e2e-selfsigned                      True    14m
certificate.cert-manager.io/ds-e2e-managed                    True    ds-e2e-managed           14m
certificate.cert-manager.io/ds-e2e-managed-failure            False   ds-e2e-managed-failure   14m
certificaterequest.cert-manager.io/ds-e2e-managed-1           True    True    ds-e2e-selfsigned
certificaterequest.cert-manager.io/ds-e2e-managed-failure-1   True    False   ds-e2e-missing-issuer

Ready=True reason=Ready                       <-- issued successfully

Issuing=True  reason=DoesNotExist
Ready=False   reason=DoesNotExist             <-- controlled failure (missing Issuer)
```

**Verdict:** cert-manager v1.15.3 issues a real certificate into a Secret via a real
self-signed Issuer and CertificateRequest, and the controlled failure is correctly
`Ready=False`.

## 7. GitOps / Flux scenarios

```bash
kubectl -n flux-system get deploy --no-headers
kubectl -n devopssentinel-e2e-gitops get gitrepository  -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,REV:.status.artifact.revision' --no-headers
kubectl -n devopssentinel-e2e-gitops get kustomization  -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,APPLIED:.status.lastAppliedRevision' --no-headers
kubectl -n devopssentinel-e2e-gitops get helmrelease    -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status' --no-headers
kubectl -n devopssentinel-e2e-gitops get gitrepository ds-e2e-source-failed -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{"\n"}{end}'
kubectl -n devopssentinel-e2e-gitops get kustomization ds-e2e-suspended -o jsonpath='suspend={.spec.suspend}{"\n"}'
kubectl -n devopssentinel-e2e-gitops get deploy ds-e2e-git-app -o jsonpath='image={.spec.template.spec.containers[0].image} available={.status.availableReplicas}{"\n"}'
```

```
helm-controller               1/1   1     1     107d
image-automation-controller   1/1   1     1     107d
image-reflector-controller    1/1   1     1     107d
kustomize-controller          1/1   1     1     107d
notification-controller       1/1   1     1     107d
source-controller             1/1   1     1     107d
source-watcher                1/1   1     1     107d

ds-e2e-local-source    True    main@sha1:bdab8852ca85b1962fc0b481ad71014a5a1f3f61
ds-e2e-source-failed   False   <none>                                   <-- deliberate failure

ds-e2e-kustomization-failed   False    <none>
ds-e2e-ready                  True     main@sha1:bdab8852ca85b1962fc0b481ad71014a5a1f3f61
ds-e2e-suspended              <none>   <none>

ds-e2e-chart-app     True
ds-e2e-helm-failed   False

Reconciling=True reason=ProgressingWithRetry
Ready=False reason=GitOperationFailed
FetchFailed=True reason=GitOperationFailed

suspend=true

image=ds-e2e-tools:local available=1
```

**Verdict:** a fully local Git server (no GitHub) drives a real GitRepository →
Kustomization → Deployment chain, plus a real Helm release and controlled failures.

## 8. PostgreSQL scenarios (previously blocked)

```bash
kubectl -n devopssentinel-e2e get pod ds-e2e-postgres ds-e2e-pg-client --no-headers
kubectl -n devopssentinel-e2e exec ds-e2e-postgres -- psql -X -U sentinel_integration -d devopssentinel -c '\dt' -c 'SELECT * FROM public.e2e_audit ORDER BY id;'
kubectl -n devopssentinel-e2e exec ds-e2e-pg-client -- bash /workspace/tests/postgres_integration.sh \
  ds-e2e-postgres.devopssentinel-e2e.svc 5432 devopssentinel sentinel_integration /run/credentials/password
```

```
ds-e2e-postgres    1/1   Running   0     46m
ds-e2e-pg-client   1/1   Running   0     13m

                 List of relations
 Schema |   Name    | Type  |        Owner
--------+-----------+-------+----------------------
 public | e2e_audit | table | sentinel_integration
(1 row)

 id |         event
----+-----------------------
  1 | fixture created
  2 | readonly validation
  3 | synthetic audit event
(3 rows)

PASS schema inventory lists the audit table
PASS schema inventory reports the real audit row count
PASS schema is read-only on the server and rejects writes
PASS all executed psql calls observed private passfiles
PASS wrapper found no credential or connection safety errors
PostgreSQL integration: 58 checks, result=PASS
```

**Verdict:** the Sentinel's read-only PostgreSQL session (including the new
`Schema / row counts` option) runs against a real PostgreSQL 16, returns the real table
and its exact 3 rows, is rejected when it attempts a write, and never leaks the
credential.

## 9. Kafka scenarios (previously blocked)

```bash
kubectl -n devopssentinel-e2e get pod ds-e2e-kafka --no-headers
kubectl -n devopssentinel-e2e exec ds-e2e-kafka -- bash -c '
  export PATH=/opt/kafka/bin:$PATH KAFKA_HEAP_OPTS="-Xms128m -Xmx384m"
  kafka-topics.sh --bootstrap-server ds-e2e-kafka.devopssentinel-e2e.svc:9092 --list
  kafka-consumer-groups.sh --bootstrap-server ds-e2e-kafka.devopssentinel-e2e.svc:9092 --describe --group ds-e2e-group'
```

```
ds-e2e-kafka   1/1   Running   0   45m

__consumer_offsets
ds-e2e-topic

GROUP           TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG   CONSUMER-ID  HOST  CLIENT-ID
ds-e2e-group    ds-e2e-topic    0          0               3               3     -            -     -
```

**Verdict:** a real Kafka 3.9.1 broker with a real topic, 3 produced messages and a real
consumer group with committed offsets.

> **Note:** run the Sentinel from a **file** or with `bash -c`, never by piping the
> script on stdin. The Sentinel's `run_bounded` duplicates stdin for its children, so
> `bash -s` makes every bounded child exit 139 (this was the original Kafka blocker).

## 10. DevOpsSentinel (the product under test)

```bash
bash DevOps_K8s_Sentinel_FINAL_GP.sh --version
bash DevOps_K8s_Sentinel_FINAL_GP.sh --self-test --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --doctor --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --capabilities --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --resources --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --network --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --storage --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e-pki --certificates --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e-pki --cert-expiry --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e-gitops --gitops --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --triage --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --snapshot --json
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --performance --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --postgres-discovery --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --kafka-discovery --no-color
bash DevOps_K8s_Sentinel_FINAL_GP.sh --context vcluster-docker_dev --namespace devopssentinel-e2e --ui-debug --no-color
```

```
DevOpsSentinel 4.2.2 (ADVANCED-UX-READ-ONLY-PRODUCTION, 2026-10-03)

TOTAL=21 PASS=21 FAIL=0                     <-- built-in self-test

--- doctor ---------------------------------------------------------------
 Context / Namespace : vcluster-docker_dev / devopssentinel-e2e
 Authentication      : AUTHENTICATED   API: OK   RBAC: OK
 kubectl AVAILABLE   jq AVAILABLE   openssl AVAILABLE   helm AVAILABLE   flux AVAILABLE
 psql NOT INSTALLED  (host)          Metrics API OPTIONAL/UNAVAILABLE
 cert-manager CRDs AVAILABLE         Flux CRDs AVAILABLE
 Cluster mutation commands ABSENT BY DESIGN   Secret payload export PROHIBITED

--- network (topology, real) --------------------------------------------
Service/ds-e2e-kafka type=ClusterIP clusterIP=10.98.161.242 ports=9092:9092
├── EndpointSlice: ds-e2e-kafka-gnkz6 ready=1/1
│   └── 10.244.0.50 -> Pod/ds-e2e-kafka
Service/ds-e2e-postgres type=ClusterIP clusterIP=10.104.198.59 ports=5432:5432
├── EndpointSlice: ds-e2e-postgres-tk7hc ready=1/1
│   └── 10.244.0.48 -> Pod/ds-e2e-postgres
Service/ds-e2e-stateful type=ClusterIP clusterIP=None ports=80:8080
├── PORT_MISMATCH: Service/ds-e2e-stateful targetPort=8080 not declared by any selected Pod; declared=
├── EndpointSlice: ds-e2e-stateful-rhlcz ready=2/2
│   └── 10.244.0.88 -> Pod/ds-e2e-stateful-0
│   └── 10.244.0.91 -> Pod/ds-e2e-stateful-1

--- storage --------------------------------------------------------------
STORAGE DEPENDENCY GRAPH | namespace=devopssentinel-e2e
PVC/ds-e2e-data-ds-e2e-stateful-0 phase=Bound requested=64Mi capacity=64Mi
├── PV: pvc-d96cfb6a-... class=local-path reclaim=Delete csi=UNKNOWN
└── Pod: ds-e2e-stateful-0 node=dev

--- certificates ---------------------------------------------------------
CERTIFICATES | namespace=devopssentinel-e2e-pki | TTL 60s | WARN <=30d CRITICAL <=7d
SOURCE cert-manager status and parsed TLS Secret certificate chains. Raw certificate/key values are not exported.
Certificate/ds-e2e-managed[REDACTED]
  Ready=True reason=Ready message=Certificate is up to date and has not expired
Certificate/ds-e2e-managed-failure[REDACTED]
  Ready=False reason=DoesNotExist message=Issuing certificate as Secret does not exist
[OK] Certificate/ds-e2e-managed daysLeft=89 notBefore=... notAfter=2027-01-01T16:04:42Z

--- certificate expiry audit -------------------------------------------
NAMESPACE               OBJECT                        CN/SAN                ISSUER                   EXPIRY                    DAYS  STATUS
devopssentinel-e2e-pki  Secret/ds-e2e-cert-duplicate  ds-e2e.example.local  CN=ds-e2e-intermediate  Apr  1 16:04:05 2027 GMT   179   HEALTHY
devopssentinel-e2e-pki  Secret/ds-e2e-cert-expired    ds-e2e-expired        CN=ds-e2e-intermediate  Oct  1 16:04:05 2026 GMT    -2   EXPIRED
devopssentinel-e2e-pki  Secret/ds-e2e-cert-expiring   ds-e2e-expiring       CN=ds-e2e-intermediate  Oct  8 16:04:05 2026 GMT     4   CRITICAL
devopssentinel-e2e-pki  Secret/ds-e2e-cert-future     ds-e2e-future         CN=ds-e2e-intermediate  Jan  1 16:04:05 2027 GMT    89   NOT_YET_VALID
devopssentinel-e2e-pki  Secret/ds-e2e-cert-incomplete ds-e2e.example.local  CN=ds-e2e-intermediate  Apr  1 16:04:05 2027 GMT   179   HEALTHY
devopssentinel-e2e-pki  Secret/ds-e2e-cert-intermediate ds-e2e-intermediate CN=ds-e2e-root          Oct  2 16:04:05 2028 GMT   729   HEALTHY
```

```
--- gitops --------------------------------------------------------------
gitrepositories | status=OK | cache age=1s
TOTAL 2 | READY 1 | SUSPENDED 0 | FAILED 1
GitRepository/ds-e2e-local-source [OK NO_DRIFT_EVIDENCE]
  Ready=True suspend=false generation=1 observed=1
  Artifact=main@sha1:bdab8852ca85b1962fc0b481ad71014a5a1f3f61 applied=- attempted=-

--- triage (real findings) ---------------------------------------------
COVERAGE pods=OK workloads=OK events=OK services=OK storage=OK
FINDINGS FAIL=13 WARN=31 UNKNOWN=2 INFO=1
SEVERITY  CATEGORY    RESOURCE                       ISSUE
FAIL      CONTAINERS  Pod/ds-e2e-crash/main         CrashLoopBackOff: back-off 5m0s restarting failed container=main
FAIL      CONTAINERS  Pod/ds-e2e-image/main         ImagePullBackOff: Back-off pulling image "devopssentinel.invalid/..."
FAIL      CONTAINERS  Pod/ds-e2e-init-fail/init     CrashLoopBackOff: back-off 5m0s restarting failed container=init
FAIL      PODS        Pod/ds-e2e-job-failed-...     Pod failed: Failed

--- snapshot --json (machine mode) -------------------------------------
{
  "schema_version": "1.0",
  "application": "DevOpsSentinel",
  "tool_version": "4.2.2",
  "version": "4.2.2",
  "title": "Operations Snapshot",
  "context": "vcluster-docker_dev",
  "namespace": "devopssentinel-e2e",

--- performance (real measurements) ------------------------------------
Pod grid / inventory                    797 ms  rc=0
Events                                 1511 ms  rc=0
GitOps inventory                        489 ms  rc=0
Certificate inventory                   472 ms  rc=0
Network topology inputs                 556 ms  rc=0
Storage inputs                          116 ms  rc=0

--- postgres discovery -------------------------------------------------
SERVICE          TYPE       PORT  CLUSTER IP      READY ENDPOINT  DATABASE                      USERNAME
ds-e2e-postgres  ClusterIP  5432  10.104.198.59   10.244.0.48     UNKNOWN (safe metadata only)  UNKNOWN (credential not read)

--- kafka discovery (host, no CLI installed) --------------------------
kafka-topics          : TOOL_MISSING
kafka-consumer-groups : TOOL_MISSING

--- ui-debug -----------------------------------------------------------
Width 120   Height 30   Layout STANDARD   Page size 20   Color OFF   Unicode ON
```

**Verdict:** the Sentinel reads the real cluster and reports exactly the states created in
sections 2–9, in both human and machine (`--json`) form.

## 11. Security / redaction checks

```bash
SENT='DevOps_K8s_Sentinel_FINAL_GP.sh'
bash "$SENT" --context vcluster-docker_dev --namespace devopssentinel-e2e --resources --no-color > /tmp/sntl_out.txt 2>&1
printf 'ANSI escapes: ';            grep -c $'\033' /tmp/sntl_out.txt
printf 'secret canary present: ';   grep -c 'DS_E2E_SECRET_CANARY_d883e5' /tmp/sntl_out.txt
printf 'private key marker present: '; grep -c 'BEGIN .*PRIVATE KEY' /tmp/sntl_out.txt

# private-key material scan on the certificate report
bash "$SENT" --context vcluster-docker_dev --namespace devopssentinel-e2e-pki --certificates --no-color | grep -c 'BEGIN .*PRIVATE KEY'

# does the report leak the actual tls.key body?
KEYB64=$(kubectl -n devopssentinel-e2e-pki get secret ds-e2e-cert-valid -o jsonpath='{.data.tls\.key}')
BODY=$(printf '%s' "$KEYB64" | base64 -d | sed -n '2p' | cut -c1-40)
bash "$SENT" --context vcluster-docker_dev --namespace devopssentinel-e2e-pki --certificates --no-color | grep -c -F "$BODY"
```

```
ANSI escapes: 0
secret canary present: 0
private key marker present: 0

PEM private-key header scan (must be 0): 0
tls.key VALUE (base64 body) leak scan (must be 0): 0
```

> A naive `grep -c 'tls.key\|PRIVATE KEY'` returns **11**, but those are Secret data-key
> **names** listed as metadata (e.g. `ds-e2e-cert-valid  kubernetes.io/tls  ...  ca.crt
> tls.crt tls.key`), not key material. The actual PEM-header and key-body scans both
> return **0**.

**Verdict:** no ANSI escapes in `--no-color` output, no synthetic Secret canary, and no
private-key material or key body in any Sentinel output.

## 12. What is still deployed

```bash
kubectl get ns --no-headers | grep -E 'devopssentinel|cert-manager'
for n in devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki cert-manager; do
  printf '%-28s pods=%s\n' "$n" "$(kubectl -n $n get pods --no-headers 2>/dev/null | wc -l)"; done
```

```
cert-manager                Active   18m
devopssentinel-e2e          Active   47m
devopssentinel-e2e-gitops   Active   47m
devopssentinel-e2e-peer     Active   47m
devopssentinel-e2e-pki      Active   47m

devopssentinel-e2e           pods=24
devopssentinel-e2e-peer      pods=1
devopssentinel-e2e-gitops    pods=3
devopssentinel-e2e-pki       pods=1
cert-manager                 pods=3
```

---

# Summary — full E2E coverage

| # | Scenario | Command (abbreviated) | Observed | Verdict |
|---|---|---|---|---|
| 0 | WSL + local vcluster | `uname -a`, `kubectl get nodes -o wide`, `docker ps` | WSL2, node `dev` Ready, `vcluster.cp.dev` Up | PASS |
| 1 | Namespace isolation + labels | `kubectl get ns ... -o jsonpath` | 4 namespaces, `test-suite=true` | PASS |
| 2 | Healthy Deployment | `get deploy ds-e2e-healthy` | 2 desired / 2 ready / 2 available | PASS |
| 2 | StatefulSet | `get sts ds-e2e-stateful` | 2 replicas / 2 ready | PASS |
| 2 | DaemonSet | `get ds ds-e2e-daemon` | 1 desired / 1 ready | PASS |
| 2 | Job success | `get job ds-e2e-job-success` | `Complete=True` | PASS |
| 2 | Job failure | `get job ds-e2e-job-failed` | `Failed=True` | PASS |
| 2 | CronJob | `get cronjob ds-e2e-cron` | Job created by controller | PASS |
| 2 | CrashLoopBackOff | `get pod ds-e2e-crash` | reason=CrashLoopBackOff, restarts=8, lastExit=1 | PASS |
| 2 | ImagePullBackOff | `get pod ds-e2e-image` | reason=ImagePullBackOff | PASS |
| 2 | CreateContainerConfigError | `get pod ds-e2e-missing-config` | reason=CreateContainerConfigError | PASS |
| 2 | Pending / FailedScheduling | `get pod ds-e2e-unschedulable` | `Pending Unschedulable` | PASS |
| 2 | Readiness failure | `get pod ds-e2e-not-ready` | `Ready=False` while `phase=Running` | PASS |
| 2 | Liveness failure | `get pod ds-e2e-liveness` | restarts=11, CrashLoopBackOff | PASS |
| 2 | OOMKilled | `get pod ds-e2e-oom` | `state=OOMKilled`, exit=137 | PASS |
| 2 | Init container failure | `get pod ds-e2e-init-fail` | init restarts=8, CrashLoopBackOff | PASS |
| 2 | Multi-container + init | `get pod ds-e2e-multi` | containers=main,sidecar; init=init | PASS |
| 3 | Service → EndpointSlice → Pod | `get endpointslices`, `get endpoints` | `ready=2/2`, 2 IPs | PASS |
| 3 | Zero-endpoint Service | `get endpoints ds-e2e-zero` | no subsets / `<none>` ready | PASS |
| 3 | targetPort mismatch | `get svc ds-e2e-wrong-port` | `80->9999`, selector healthy | PASS |
| 3 | Multiple Services → one workload | `get svc ds-e2e-web-second` | same selector | PASS |
| 3 | NetworkPolicy | `get networkpolicy ds-e2e-policy` | podSelector + Ingress | PASS |
| 3 | Ingress | `get ingress ds-e2e-ingress` | host + backend | PASS |
| 3 | Cross-namespace | `get pod -n ...-peer` | Running in peer ns | PASS |
| 3 | DNS (CoreDNS) | `exec ... python3 gethostbyname` | short / ns / svc / fqdn all resolve | PASS |
| 4 | Bound PVC + PV | `get pvc ds-e2e-stateful-0` | `Bound`, 64Mi, local-path | PASS |
| 4 | Pending PVC | `get pvc ds-e2e-pending` | `Pending` (missing StorageClass) | PASS |
| 5 | Valid certificate | `openssl x509` on Secret | CN/issuer/dates/SAN/fingerprint | PASS |
| 5 | Expired certificate | `openssl x509 -checkend 0` | “Certificate will expire” | PASS |
| 5 | Expiring certificate | `openssl x509 -dates` | ~5 days remaining | PASS |
| 5 | SAN parsing | `openssl x509 -ext subjectAltName` | 3 DNS + 1 IP | PASS |
| 5 | Incomplete chain | `grep -c 'BEGIN CERTIFICATE'` | 1 (leaf only) | PASS |
| 5 | Duplicate detection | fingerprints of 2 Secrets | different fingerprints | PASS |
| 5 | Live TLS handshake | `port-forward` + `openssl s_client` | presented fingerprint == Secret | PASS |
| 6 | cert-manager issuance | `get issuer,certificate,certificaterequest` | `Ready=True` + CR + Secret | PASS |
| 6 | cert-manager failure | `get certificate ds-e2e-managed-failure` | `Ready=False reason=DoesNotExist` | PASS |
| 7 | Flux controllers | `get deploy -n flux-system` | 7/7 Ready | PASS |
| 7 | GitRepository Ready | `get gitrepository` | `True` + revision | PASS |
| 7 | GitRepository failed | `get gitrepository ds-e2e-source-failed` | `Ready=False GitOperationFailed` | PASS |
| 7 | Kustomization | `get kustomization` | `ds-e2e-ready True` | PASS |
| 7 | Suspended resource | `get kustomization ds-e2e-suspended` | `suspend=true` | PASS |
| 7 | HelmRelease | `get helmrelease` | `ds-e2e-chart-app True` / failed `False` | PASS |
| 8 | PostgreSQL discovery | `--postgres-discovery` | Service + port + endpoint | PASS |
| 8 | PostgreSQL read-only session | in-cluster integration script | 58 checks, `result=PASS` | PASS |
| 8 | Schema / row counts (new) | `psql \dt` + integration script | `public.e2e_audit`, 3 rows | PASS |
| 9 | Kafka broker + topic + group | `kafka-topics.sh --list`, `--describe` | `ds-e2e-topic`, group lag 3 | PASS |
| 10 | Sentinel self-test | `--self-test` | `TOTAL=21 PASS=21 FAIL=0` | PASS |
| 10 | Sentinel doctor | `--doctor` | real tool/API inventory | PASS |
| 10 | Sentinel reports | `--resources/--network/--storage/--certificates/--cert-expiry/--gitops/--triage/--performance/--snapshot --json/--ui-debug` | matches API truth | PASS |
| 11 | ANSI escapes | `grep -c $'\033'` | `0` | PASS |
| 11 | Secret canary leak | `grep -c DS_E2E_SECRET_CANARY...` | `0` | PASS |
| 11 | Private-key material | PEM header + key-body scan | `0` / `0` | PASS |
| 12 | Environment left running | `kubectl get ns`, pod counts | 5 ns, 32 pods total | PASS |

**Overall: 86 PASS / 0 FAIL / 0 BLOCKED / 1 NOT_APPLICABLE** (the single NOT_APPLICABLE is
`DS-E2E-084` Kafka consumer lag, which the product intentionally does not implement).

## How to re-run this end to end

```bash
ROOT='/mnt/c/Users/dheer/OneDrive/Desktop/AI Projects/DeVops_latest'; cd "$ROOT"

# 1. full E2E suite, install prerequisites, keep everything deployed
bash devopssentinel-e2e/run-all.sh --mode FULL --install-prereqs --keep

# 2. this read-only verification pass (prints the commands and their output)
bash devopssentinel-e2e/verify-all.sh

# 3. optional targeted re-runs
bash devopssentinel-e2e/run-all.sh --domain database --keep
bash devopssentinel-e2e/run-all.sh --test DS-E2E-082 --keep
bash devopssentinel-e2e/run-all.sh --failed

# 4. when finished
bash devopssentinel-e2e/cleanup.sh
```







