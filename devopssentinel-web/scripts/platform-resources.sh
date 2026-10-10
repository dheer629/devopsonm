#!/usr/bin/env bash
# DevOpsSentinel Web -- optional platform fixtures.
#
# Deploys a small, self-contained set of *real* objects so every domain page
# (Workloads, Pods, Storage, Network, Database, PKI, Kafka, Events) has
# something to discover. The Sentinel engine itself stays read-only; this script
# performs the explicitly scoped setup, mirroring devopssentinel-e2e/ fixtures.
#
#   scripts/platform-resources.sh up   [NAMESPACE]   # default namespace: default
#   scripts/platform-resources.sh down [NAMESPACE]
#   scripts/platform-resources.sh pvc  [NAMESPACE] [NAME] [SIZE]
#
# `up` also seeds a small PostgreSQL schema (scripts/seed-platform-data.sh) and
# creates Kafka topics, records and a consumer group, so the Database and Kafka
# pages have real data. PostgreSQL and Kafka both persist to PersistentVolumes,
# so the data survives a pod or cluster restart.
#
# Images are pinned to what is already present in the local cluster so no
# registry access is required. Everything carries the label
# `devopssentinel.io/platform=true` for one-command cleanup.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MANIFEST="$SCRIPT_DIR/../deploy/platform/platform.yaml"
CERT_MANAGER_MANIFEST="$SCRIPT_DIR/../deploy/platform/cert-manager.yaml"
ACTION="${1:-up}"
NS="${2:-default}"
LABEL="devopssentinel.io/platform=true"

log() { printf '[platform-resources] %s\n' "$*"; }

command -v kubectl >/dev/null 2>&1 || { printf 'kubectl is required on PATH\n' >&2; exit 3; }
[[ -f "$MANIFEST" ]] || { printf 'manifest not found: %s\n' "$MANIFEST" >&2; exit 3; }

kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS" >/dev/null

if [[ "$ACTION" == "down" ]]; then
    log "removing platform fixtures from namespace $NS"
    if kubectl get crd certificates.cert-manager.io >/dev/null 2>&1; then
        kubectl delete -n "$NS" -l "$LABEL" certificate,issuer --ignore-not-found >/dev/null || true
        kubectl delete -l "$LABEL" clusterissuer --ignore-not-found >/dev/null || true
    fi
    kubectl delete -n "$NS" -l "$LABEL" \
        deployment,service,secret,persistentvolumeclaim,configmap \
        --ignore-not-found >/dev/null || true
    log "done"
    exit 0
fi

if [[ "$ACTION" == "pvc" ]]; then
    # scripts/platform-resources.sh pvc <namespace> <name> [size]
    NAME="${3:-platform-pvc}"
    SIZE="${4:-1Gi}"
    log "creating PersistentVolumeClaim $NAME ($SIZE) in $NS"
    kubectl apply -n "$NS" -f - <<YAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $NAME
  labels:
    devopssentinel.io/platform: "true"
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: local-path
  resources:
    requests:
      storage: $SIZE
YAML
    kubectl -n "$NS" get pvc "$NAME" || true
    log "note: the local-path provisioner binds on first consumer, so a PVC with no"
    log "      consuming pod stays Pending — which the Storage page reports as WARNING."
    log "done"
    exit 0
fi

[[ "$ACTION" == "up" ]] || { printf 'usage: %s {up|down|pvc} [NAMESPACE] [NAME] [SIZE]\n' "$0" >&2; exit 2; }

NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
NODE_IP=${NODE_IP:-127.0.0.1}
log "applying platform fixtures to namespace $NS (node IP $NODE_IP)"
sed "s/__NODE_IP__/$NODE_IP/g" "$MANIFEST" | kubectl apply -n "$NS" -f -

# Optional cert-manager objects (a self-signed ClusterIssuer + a managed
# Certificate) so the PKI / TLS page shows a real, issuer-backed certificate
# alongside the hand-made TLS Secret. Applied only when the CRDs are installed.
if [[ -f "$CERT_MANAGER_MANIFEST" ]] && kubectl get crd certificates.cert-manager.io >/dev/null 2>&1; then
    log "cert-manager CRDs detected; applying the managed Certificate fixture"
    kubectl apply -f "$CERT_MANAGER_MANIFEST" >/dev/null 2>&1 || log "  cert-manager fixtures could not be applied"
    kubectl -n "$NS" wait --for=condition=Ready certificate/platform-cert --timeout=180s >/dev/null 2>&1 \
        || log "  the managed Certificate is not Ready yet (issuer may still be starting)"
else
    log "cert-manager CRDs not installed; skipping the managed Certificate fixture"
fi

# TLS Secret (PKI / TLS page). Generated locally; the private key never leaves
# the cluster and is never read back by the read-only adapter.
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$tmp/tls.key" -out "$tmp/tls.crt" \
    -subj "/CN=sentinel.internal/O=DevOpsSentinel Platform" \
    -addext "subjectAltName=DNS:sentinel.internal,DNS:platform-web.$NS.svc" \
    >/dev/null 2>&1
kubectl create secret tls platform-tls \
    --cert="$tmp/tls.crt" --key="$tmp/tls.key" \
    -n "$NS" --dry-run=client -o yaml | kubectl apply -n "$NS" -f - >/dev/null
kubectl -n "$NS" label secret platform-tls devopssentinel.io/platform=true --overwrite >/dev/null

log "waiting for platform workloads to become ready"
kubectl -n "$NS" rollout status deployment/platform-web --timeout=120s || true
kubectl -n "$NS" rollout status deployment/platform-postgres --timeout=120s || true
kubectl -n "$NS" rollout status deployment/platform-kafka --timeout=240s || true

# Real tables and rows, so the Database page (and the opt-in SQL console) has
# something meaningful to show. Idempotent: it drops and recreates the schema.
log "seeding the platform PostgreSQL schema"
if ! bash "$SCRIPT_DIR/seed-platform-data.sh" "$NS" >/dev/null 2>&1; then
    log "  seed skipped - run scripts/seed-platform-data.sh $NS manually"
fi

# Platform topics, records and a consumer group, so the opt-in Topics view and
# the Kafka diagnostics have something real to read. Everything goes through the
# broker's own CLI, so this works even when the workstation has no Kafka tools.
KAFKA_POD=$(kubectl -n "$NS" get pods -l app=platform-kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$KAFKA_POD" ]]; then
    log "creating platform topics on $KAFKA_POD"
    for topic in orders payments events audit-log; do
        kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-topics.sh \
            --bootstrap-server localhost:9092 --create --if-not-exists \
            --topic "$topic" --partitions 3 --replication-factor 1 >/dev/null 2>&1 || true
    done
    log "producing 25 platform records into orders, payments and events"
    for topic in orders payments events; do
        for seq in $(seq 1 25); do
            printf '{"topic":"%s","seq":%s,"source":"platform-seed"}\n' "$topic" "$seq"
        done | kubectl -n "$NS" exec -i "$KAFKA_POD" -- \
            /opt/kafka/bin/kafka-console-producer.sh \
            --bootstrap-server localhost:9092 --topic "$topic" >/dev/null 2>&1 || true
    done
    log "committing offsets for the platform-reader consumer group"
    kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 --topic orders --group platform-reader \
        --from-beginning --max-messages 10 --timeout-ms 15000 >/dev/null 2>&1 || true
fi

log "local (NodePort) endpoints for the opt-in views:"
log "  PostgreSQL  ${NODE_IP}:30432   (user/db/password: platform)"
log "  Kafka       ${NODE_IP}:30092"

log "objects in namespace $NS:"
kubectl -n "$NS" get deploy,svc,pvc,secret -l "$LABEL" 2>/dev/null || true
log "done"
