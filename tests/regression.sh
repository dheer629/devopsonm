#!/usr/bin/env bash
# Deterministic regressions. No cluster access is made by this test.
set -o pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/DevOps_K8s_Sentinel_FINAL_GP.sh"
OUTPUT_DIR=$(mktemp -d "$HOME/.devopsonm-regression.XXXXXXXX") || exit 1
init_runtime || exit 1
test_root=$OUTPUT_DIR
trap 'cleanup; rm -rf -- "$test_root"' EXIT
fail=0
check() { if "$@"; then printf 'PASS %s\n' "$*"; else printf 'FAIL %s\n' "$*"; fail=1; fi; }
check selftest_home_runtime
cache_record pods OK
check validation_cache_result 0 pods
cache_record pods RBAC_DENIED
validation_cache_result 0 pods > "$RUN_DIR/denied.txt"; rc=$?
check test "$rc" -eq 4
check grep -q RBAC_DENIED "$RUN_DIR/denied.txt"
cache_record optional RESOURCE_NOT_FOUND
validation_cache_result 1 optional > "$RUN_DIR/optional.txt"; rc=$?
check test "$rc" -eq 0
check grep -q OPTIONAL_UNAVAILABLE "$RUN_DIR/optional.txt"
validation_cache_result 0 optional >/dev/null; rc=$?
check test "$rc" -eq 4
# The original live validator incorrectly passed collectors ending in `|| :`.
collect_pods() { cache_record pods RBAC_DENIED; :; }
collect_workloads() { cache_record workloads OK; }
collect_events() { cache_record events EMPTY_RESULT; }
collect_network() { for key in services endpointslices endpoints ingresses; do cache_record "$key" EMPTY_RESULT; done; }
collect_storage() { cache_record pvcs EMPTY_RESULT; }
gitops_collect() { for key in flux_gitrepositories flux_kustomizations flux_helmrepositories flux_helmreleases; do cache_record "$key" RESOURCE_NOT_FOUND; done; }
cert_manager_collect() { for key in cert_certificates cert_certificaterequests cert_issuers cert_clusterissuers; do cache_record "$key" RESOURCE_NOT_FOUND; done; }
tls_secret_metadata_collect() { return 0; }
live_validation_report > "$RUN_DIR/validation.txt"; rc=$?
check test "$rc" -eq 4
check grep -q 'pods=RBAC_DENIED PARTIAL/FAIL' "$RUN_DIR/validation.txt"
# Pending PVCs and unavailable PV reads must still show up in the graph.
collect_storage() { :; }
collect_pods() { :; }
kctl_cluster() { printf '{"items":[]}\n'; }
cache_record pvcs OK
cache_record pods EMPTY_RESULT
printf '{"items":[{"metadata":{"name":"pending"},"spec":{"resources":{"requests":{"storage":"1Gi"}}},"status":{"phase":"Pending"}}]}\n' > "$CACHE_DIR/pvcs.json"
printf '{"items":[]}\n' > "$CACHE_DIR/pods.json"
storage_dependency_report > "$RUN_DIR/storage.txt"
check grep -q 'PVC/pending phase=Pending' "$RUN_DIR/storage.txt"
check grep -q 'PV: UNBOUND' "$RUN_DIR/storage.txt"
# Ownerless Pods must not crash workload dependency queries; ReplicaSet and
# Deployment references must both resolve Services through their matching pods.
collect_network() { :; }
collect_workloads() { :; }
deployment_chain_report() { :; }
printf '%s\n' '{"items":[{"metadata":{"name":"standalone"},"spec":{},"status":{}},{"metadata":{"name":"app-pod","labels":{"app":"platform"},"ownerReferences":[{"kind":"ReplicaSet","name":"platform-rs","controller":true}]},"spec":{"containers":[{"name":"app","image":"test"}]},"status":{"phase":"Running"}}]}' > "$CACHE_DIR/pods.json"
printf '%s\n' '{"items":[{"kind":"ReplicaSet","metadata":{"name":"platform-rs","ownerReferences":[{"kind":"Deployment","name":"platform","controller":true}]}}]}' > "$CACHE_DIR/workloads.json"
printf '%s\n' '{"items":[{"metadata":{"name":"platform-svc"},"spec":{"selector":{"app":"platform"}}}]}' > "$CACHE_DIR/services.json"
for key in pods workloads services; do cache_record "$key" OK; done
for target in Deployment/platform ReplicaSet/platform-rs; do
    resource_dependencies "${target%/*}" fixture "${target#*/}" > "$RUN_DIR/dependency.txt" 2>&1; rc=$?
    check test "$rc" -eq 0
    check grep -q 'Service: platform-svc' "$RUN_DIR/dependency.txt"
    check grep -q 'Pod: app-pod' "$RUN_DIR/dependency.txt"
    if grep -q 'jq: error' "$RUN_DIR/dependency.txt"; then fail=1; fi
done
# Enforce read-only and scope boundaries without invoking kubectl.
for args in '--namespace=other' '--context=other' '--token=fake' '--raw=/api' '--watch'; do
    scope_args_safe "$args" >/dev/null 2>&1; rc=$?
    check test "$rc" -eq 2
done
SENTINEL_CONTEXT=fixture SENTINEL_NAMESPACE=fixture
kctl_dispatch ns delete pods >/dev/null 2>&1; rc=$?
check test "$rc" -eq 2
exit "$fail"
