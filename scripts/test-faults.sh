#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONTEXT=${1:-vcluster-docker_dev}
NAMESPACE=devopsonm
kube=(kubectl --context "$CONTEXT" -n "$NAMESPACE")
# Refuse to overwrite resources that were not created by this invocation.
for resource in pod/sentinel-failed pvc/sentinel-pending secret/sentinel-test-tls secret/sentinel-canary; do
    if "${kube[@]}" get "$resource" >/dev/null 2>&1; then
        printf 'Fixture already exists: %s; no changes made\n' "$resource" >&2
        exit 2
    fi
done
umask 077
scratch=$(mktemp -d "$HOME/.sentinel-e2e.XXXXXXXX")
cleanup_fixtures() {
    "${kube[@]}" delete -f "$ROOT/tests/fixtures/faults.yaml" --ignore-not-found --wait=false >/dev/null
    "${kube[@]}" delete secret sentinel-test-tls sentinel-canary --ignore-not-found >/dev/null
    rm -rf -- "$scratch"
}
trap cleanup_fixtures EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 5 -subj /CN=sentinel-e2e.invalid \
    -keyout "$scratch/tls.key" -out "$scratch/tls.crt" >/dev/null 2>&1
"${kube[@]}" create secret tls sentinel-test-tls --key="$scratch/tls.key" --cert="$scratch/tls.crt"
printf 'SENTINEL_E2E_CANARY_DO_NOT_EXPORT' > "$scratch/password"
"${kube[@]}" create secret generic sentinel-canary --from-file=password="$scratch/password"
"${kube[@]}" apply -f "$ROOT/tests/fixtures/faults.yaml"
"${kube[@]}" wait --for=jsonpath='{.status.phase}'=Failed pod/sentinel-failed --timeout=60s
python3 "$ROOT/tests/e2e.py" --context "$CONTEXT" --namespace "$NAMESPACE" --workload sentinel-platform --fault-fixtures
