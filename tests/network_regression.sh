#!/usr/bin/env bash
# Kafka client failures and input validation; no running broker required.
set -o pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT/DevOps_K8s_Sentinel_FINAL_GP.sh"
OUTPUT_DIR=$(mktemp -d "$HOME/.sentinel-network.XXXXXXXX") || exit 1
init_runtime || exit 1
test_root=$OUTPUT_DIR
trap 'cleanup; rm -rf -- "$test_root"' EXIT
fail=0 total=0
check() { ((total+=1)); if "$@"; then printf 'PASS %s\n' "$*"; else printf 'FAIL %s\n' "$*"; fail=1; fi; }
for valid in example.invalid:9092 127.0.0.1:1 '[::1]:9092' 'a:1,b:65535'; do
    check kafka_valid_bootstrap "$valid"
done
for invalid in 'host' 'host:0' 'host:65536' 'host:1,' ',host:1' 'host:1,,b:2' 'host:1,b:0' '--option:9092'; do
    kafka_valid_bootstrap "$invalid"; rc=$?
    check test "$rc" -ne 0
done
# An actual executable ensures the wrapper preserves external exit codes and
# redacts stderr. The fixture's literal credential marker is not a real secret.
cat > "$RUN_DIR/failing-client" <<'CLIENT'
#!/bin/sh
printf 'password=sentinel-client-canary\n' >&2
exit 21
CLIENT
chmod 700 "$RUN_DIR/failing-client"
kafka_topics_bin() { printf '%s/failing-client\n' "$RUN_DIR"; }
kafka_groups_bin() { printf '%s/failing-client\n' "$RUN_DIR"; }
for fn in kafka_topics_report kafka_groups_report; do
    "$fn" example.invalid:9092 > "$RUN_DIR/client.txt"; rc=$?
    check test "$rc" -eq 21
    check grep -q REDACTED "$RUN_DIR/client.txt"
    if grep -q sentinel-client-canary "$RUN_DIR/client.txt"; then fail=1; fi
    "$fn" example.invalid:9092 "$RUN_DIR/not-present.properties" > "$RUN_DIR/config.txt"; rc=$?
    check test "$rc" -eq 2
done
kafka_topics_bin() { :; }; kafka_groups_bin() { :; }
kafka_topics_report example.invalid:9092 >/dev/null; rc=$?
check test "$rc" -eq 4
kafka_groups_report example.invalid:9092 >/dev/null; rc=$?
check test "$rc" -eq 4
# A failed second bootstrap endpoint must not be hidden by the first result.
run_bounded() {
    case "${@: -1}" in 9092) return 0;; *) printf 'connection refused\n' >&2; return 1;; esac
}
kafka_connectivity_report a:9092,b:9093 > "$RUN_DIR/connection.txt"; rc=$?
check test "$rc" -eq 1
check grep -q 'BOOTSTRAP: b:9093' "$RUN_DIR/connection.txt"
check grep -q 'TCP: NETWORK_ERROR' "$RUN_DIR/connection.txt"
printf 'Network regression checks: %s; failed=%s\n' "$total" "$fail"
exit "$fail"
