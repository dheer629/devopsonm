#!/usr/bin/env bash
# DevOpsSentinel Web -- forward an in-cluster database to the host so the
# read-only SQL console can reach it.
#
# Why this exists: the console runs its statement *server-side*, so the endpoint
# has to be reachable from the backend. A ClusterIP Service is only routable
# inside the cluster, and the container runs outside it -- so a plain ClusterIP
# times out even though it is a perfectly real address. `kubectl port-forward`
# rides the API-server connection the app already uses, so it needs no extra
# network path, no NodePort and no change to the cluster. It binds loopback only.
#
#   scripts/dsw-db-tunnel.sh [start|status|stop]
#
# Then point the console at:
#   Docker deployment : host.docker.internal:15432
#   Native run        : 127.0.0.1:15432
#
# Environment:
#   DSWEB_DB_NAMESPACE  namespace of the Service   (default: default)
#   DSWEB_DB_SERVICE    Service name               (default: postgres)
#   DSWEB_DB_PORT       host port to bind          (default: 15432)
#   DSWEB_DB_TARGET     Service port to forward    (default: 5432)
#   DSWEB_KUBECONFIG    kubeconfig                 (default: kubectl's own)
#   DSWEB_DB_SERVER     API server override, for a kubeconfig whose own server
#                       address is not reachable (e.g. a vcluster)
#   DSWEB_DB_INSECURE   set to 1 to skip TLS verify for that override
set -uo pipefail

NAMESPACE="${DSWEB_DB_NAMESPACE:-default}"
SERVICE="${DSWEB_DB_SERVICE:-postgres}"
PORT="${DSWEB_DB_PORT:-15432}"
TARGET="${DSWEB_DB_TARGET:-5432}"
LOG="${DSWEB_DB_LOG:-${TMPDIR:-/tmp}/dsw-db-tunnel.log}"

KT=(kubectl)
[[ -n "${DSWEB_KUBECONFIG:-}" ]] && KT+=(--kubeconfig "$DSWEB_KUBECONFIG")
[[ -n "${DSWEB_DB_SERVER:-}" ]] && KT+=(--server "$DSWEB_DB_SERVER")
[[ "${DSWEB_DB_INSECURE:-0}" == "1" ]] && KT+=(--insecure-skip-tls-verify)
PATTERN="port-forward svc/$SERVICE $PORT:$TARGET"

open_port() { (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null && exec 3>&- 2>/dev/null; }

status() {
  if open_port; then
    echo "RUNNING  svc/$SERVICE ($NAMESPACE) -> 127.0.0.1:$PORT"
    echo "  Docker deployment : host.docker.internal:$PORT"
    echo "  Native run        : 127.0.0.1:$PORT"
  else
    echo "STOPPED  (nothing listening on 127.0.0.1:$PORT)"
    return 1
  fi
}

case "${1:-start}" in
  status)
    status
    exit $?
    ;;
  stop)
    pkill -f "$PATTERN" 2>/dev/null || true
    sleep 1
    if open_port; then
      echo "still up on $PORT -- check: pgrep -af 'kubectl.*port-forward'"
      exit 1
    fi
    echo "Stopped (port $PORT free)."
    exit 0
    ;;
esac

pkill -f "$PATTERN" 2>/dev/null || true
sleep 1

nohup "${KT[@]}" -n "$NAMESPACE" port-forward "svc/$SERVICE" "$PORT:$TARGET" \
  > "$LOG" 2>&1 &

for _ in $(seq 1 30); do
  if open_port; then
    echo "Started."
    echo
    status
    echo
    echo "Log:  $LOG"
    echo "Stop: $0 stop"
    exit 0
  fi
  sleep 1
done

echo "failed to start; last log lines:"
tail -20 "$LOG"
exit 1
