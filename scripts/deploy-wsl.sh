#!/usr/bin/env bash
# Operator deployment command; the Sentinel utility itself remains read-only.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONTEXT=${1:-vcluster-docker_dev}
NODE_CONTAINER=${2:-vcluster.cp.dev}
IMAGE=devopsonm-sentinel:4.2.1
cd "$ROOT"
kubectl --context "$CONTEXT" get nodes
docker inspect "$NODE_CONTAINER" --format '{{.Name}}' >/dev/null
docker build -t "$IMAGE" .
docker run --rm "$IMAGE" --self-test --no-color
docker save "$IMAGE" | docker exec -i "$NODE_CONTAINER" ctr -n k8s.io images import -
kubectl --context "$CONTEXT" apply -f deploy/flux/sync.yaml
flux --context "$CONTEXT" reconcile source git devopsonm -n flux-system --timeout=2m
flux --context "$CONTEXT" reconcile kustomization devopsonm -n flux-system --timeout=4m
kubectl --context "$CONTEXT" -n devopsonm rollout status deployment/sentinel-platform --timeout=120s
job="sentinel-validation-$(date +%s)"
kubectl --context "$CONTEXT" -n devopsonm create job "$job" --from=cronjob/sentinel-validation
kubectl --context "$CONTEXT" -n devopsonm wait --for=condition=complete "job/$job" --timeout=180s
kubectl --context "$CONTEXT" -n devopsonm logs "job/$job"
