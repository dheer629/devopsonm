#!/usr/bin/env bash
# DevOpsSentinel Web -- optional demo fixtures.
#
# Deploys a small, self-contained set of *real* objects so every domain page
# (Workloads, Pods, Storage, Network, Database, PKI, Kafka, Events) has
# something to discover. The Sentinel engine itself stays read-only; this script
# performs the explicitly scoped setup, mirroring devopssentinel-e2e/ fixtures.
#
#   scripts/demo-resources.sh up   [NAMESPACE]   # default namespace: default
#   scripts/demo-resources.sh down [NAMESPACE]
#   scripts/demo-resources.sh pvc  [NAMESPACE] [NAME] [SIZE]
#
# `up` also seeds a small PostgreSQL schema (scripts/seed-demo-data.sh) and
# creates Kafka topics, records and a consumer group, so the Database and Kafka
# pages have real data. PostgreSQL and Kafka both persist to PersistentVolumes,
# so the data survives a pod or cluster restart.
#
# Images are pinned to what is already present in the demo vcluster so no
# registry access is required. Everything carries the label
# `devopssentinel.io/demo=true` for one-command cleanup.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MANIFEST="$SCRIPT_DIR/../deploy/demo/demo.yaml"
ACTION="${1:-up}"
NS="${2:-default}"
LABEL="devopssentinel.io/demo=true"

log() { printf '[demo-resources] %s\n' "$*"; }

command -v kubectl >/dev/null 2>&1 || { printf 'kubectl is required on PATH\n' >&2; exit 3; }
[[ -f "$MANIFEST" ]] || { printf 'manifest not found: %s\n' "$MANIFEST" >&2; exit 3; }

kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS" >/dev/null

if [[ "$ACTION" == "down" ]]; then
    log "removing demo fixtures from namespace $NS"
    kubectl delete -n "$NS" -l "$LABEL" \
        deployment,service,secret,persistentvolumeclaim,configmap \
        --ignore-not-found >/dev/null || true
    log "done"
    exit 0
fi

if [[ "$ACTION" == "pvc" ]]; then
    # scripts/demo-resources.sh pvc <namespace> <name> [size]
    NAME="${3:-demo-pvc}"
    SIZE="${4:-1Gi}"
    log "creating PersistentVolumeClaim $NAME ($SIZE) in $NS"
    kubectl apply -n "$NS" -f - <<YAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $NAME
  labels:
    devopssentinel.io/demo: "true"
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
log "applying demo fixtures to namespace $NS (node IP $NODE_IP)"
sed "s/__NODE_IP__/$NODE_IP/g" "$MANIFEST" | kubectl apply -n "$NS" -f -

# TLS Secret (PKI / TLS page). Generated locally; the private key never leaves
# the cluster and is never read back by the read-only adapter.
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$tmp/tls.key" -out "$tmp/tls.crt" \
    -subj "/CN=demo.sentinel.local/O=DevOpsSentinel Demo" \
    -addext "subjectAltName=DNS:demo.sentinel.local,DNS:demo-web.$NS.svc" \
    >/dev/null 2>&1
kubectl create secret tls demo-tls \
    --cert="$tmp/tls.crt" --key="$tmp/tls.key" \
    -n "$NS" --dry-run=client -o yaml | kubectl apply -n "$NS" -f - >/dev/null
kubectl -n "$NS" label secret demo-tls devopssentinel.io/demo=true --overwrite >/dev/null

log "waiting for demo workloads to become ready"
kubectl -n "$NS" rollout status deployment/demo-web --timeout=120s || true
kubectl -n "$NS" rollout status deployment/demo-postgres --timeout=120s || true
kubectl -n "$NS" rollout status deployment/demo-kafka --timeout=240s || true

# Real tables and rows, so the Database page (and the opt-in SQL console) has
# something meaningful to show. Idempotent: it drops and recreates the schema.
log "seeding the demo PostgreSQL schema"
if ! bash "$SCRIPT_DIR/seed-demo-data.sh" "$NS" >/dev/null 2>&1; then
    log "  seed skipped - run scripts/seed-demo-data.sh $NS manually"
fi

# Demo topics, records and a consumer group, so the opt-in Topics view and the
# Kafka diagnostics have something real to read. Everything goes through the
# broker's own CLI, so this works even when the workstation has no Kafka tools.
KAFKA_POD=$(kubectl -n "$NS" get pods -l app=demo-kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$KAFKA_POD" ]]; then
    log "creating demo topics on $KAFKA_POD"
    for topic in orders payments events audit-log; do
        kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-topics.sh \
            --bootstrap-server localhost:9092 --create --if-not-exists \
            --topic "$topic" --partitions 3 --replication-factor 1 >/dev/null 2>&1 || true
    done
    log "producing 25 demo records into orders, payments and events"
    for topic in orders payments events; do
        for seq in $(seq 1 25); do
            printf '{"topic":"%s","seq":%s,"source":"demo-seed"}\n' "$topic" "$seq"
        done | kubectl -n "$NS" exec -i "$KAFKA_POD" -- \
            /opt/kafka/bin/kafka-console-producer.sh \
            --bootstrap-server localhost:9092 --topic "$topic" >/dev/null 2>&1 || true
    done
    log "committing offsets for the demo-reader consumer group"
    kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 --topic orders --group demo-reader \
        --from-beginning --max-messages 10 --timeout-ms 15000 >/dev/null 2>&1 || true
fi

log "local (NodePort) endpoints for the opt-in views:"
log "  PostgreSQL  ${NODE_IP}:30432   (user/db/password: demo)"
log "  Kafka       ${NODE_IP}:30092"

log "objects in namespace $NS:"
kubectl -n "$NS" get deploy,svc,pvc,secret -l "$LABEL" 2>/dev/null || true
log "done"
