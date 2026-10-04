#!/usr/bin/env bash
# DevOpsSentinel Web -- live-data smoke test and report.
#
# Proves the opt-in live path against a real PostgreSQL and a real Kafka broker,
# and prints exactly what was written and what the API read back:
#
#   1. apply + seed the demo fixtures (idempotent)  -> what is INSERTED
#   2. insert a marker batch                        -> a known write to look for
#   3. read it back through POST /api/v1/database/query   -> what is COMING
#   4. create a topic, produce and consume records  -> broker round trip
#   5. list topics through POST /api/v1/kafka/topics
#   6. prove the read-only guards still hold
#
#   scripts/live-smoke.sh [NAMESPACE] [API_BASE]
#
# Defaults: NAMESPACE=default, API_BASE=http://127.0.0.1:8765
#
# Requires: kubectl (a context with the demo fixtures), curl, python3.
#
# Read-only note: the *application* only ever issues read-only statements and a
# single Kafka Metadata request. This script is dev tooling and is the only
# place that writes to the demo database and broker.
#
# The bundled demo endpoints are NodePorts, so they answer on a *node* address
# -- never on 127.0.0.1. The script discovers the node InternalIP and the actual
# nodePort values instead of assuming them.
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
NS="${1:-default}"
API="${2:-http://127.0.0.1:8765}"
MARKER="sentinel-smoke"

log() { printf '\n== %s ==\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl is required on PATH"
command -v python3 >/dev/null 2>&1 || die "python3 is required on PATH"

log "cluster scope (namespace $NS)"
NODE_IP=$(kubectl get nodes \
    -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
[[ -n "$NODE_IP" ]] || die "no node InternalIP -- is the context reachable?"
printf 'node address: %s\n' "$NODE_IP"

log "apply + seed the demo fixtures (this is what gets INSERTED)"
bash "$SCRIPT_DIR/demo-resources.sh" up "$NS" 2>&1 | sed -n '1,40p'

PG_POD=$(kubectl -n "$NS" get pods -l app=demo-postgres \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
KAFKA_POD=$(kubectl -n "$NS" get pods -l app=demo-kafka \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
[[ -n "$PG_POD" ]] || die "no demo-postgres pod in namespace $NS"
[[ -n "$KAFKA_POD" ]] || die "no demo-kafka pod in namespace $NS"
printf 'postgres pod: %s\nkafka pod:    %s\n' "$PG_POD" "$KAFKA_POD"

PG_NODE_PORT=$(kubectl -n "$NS" get svc postgres-nodeport -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || true)
KAFKA_NODE_PORT=$(kubectl -n "$NS" get svc kafka-nodeport -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || true)
[[ -n "$PG_NODE_PORT" ]] || die "no postgres-nodeport Service in namespace $NS"
[[ -n "$KAFKA_NODE_PORT" ]] || die "no kafka-nodeport Service in namespace $NS"
printf 'postgres endpoint: %s:%s\nkafka endpoint:    %s:%s\n' \
    "$NODE_IP" "$PG_NODE_PORT" "$NODE_IP" "$KAFKA_NODE_PORT"

log "insert a marker batch into public.demo_orders"
kubectl -n "$NS" exec -i "$PG_POD" -- \
    psql -U demo -d demo -v ON_ERROR_STOP=1 -q <<SQL
insert into public.demo_orders (customer_id, sku, quantity, amount, status)
select 1 + (g % 10), 'SKU-$MARKER-01', 1 + (g % 3), (10 + g)::numeric(10,2), 'pending'
from generate_series(1, 7) as g;
select 'inserted' as step, count(*) as marker_rows
from public.demo_orders where sku = 'SKU-$MARKER-01';
SQL

log "create topic $MARKER and produce 5 records"
kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 --create --if-not-exists \
    --topic "$MARKER" --partitions 1 --replication-factor 1 2>&1 | tail -2
for seq in 1 2 3 4 5; do
    printf '{"topic":"%s","seq":%s,"source":"live-smoke"}\n' "$MARKER" "$seq"
done | kubectl -n "$NS" exec -i "$KAFKA_POD" -- \
    /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic "$MARKER" >/dev/null 2>&1
printf 'consuming back from the beginning:\n'
kubectl -n "$NS" exec "$KAFKA_POD" -- /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 --topic "$MARKER" \
    --from-beginning --max-messages 3 --timeout-ms 15000 2>/dev/null | sed 's/^/  /'

log "read it all back through the API ($API)"
python3 - "$API" "$NODE_IP" "$PG_NODE_PORT" "$KAFKA_NODE_PORT" "$MARKER" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

api, node_ip, pg_port, kafka_port, marker = sys.argv[1:6]
failures: list[str] = []


def post(path: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{api}/api/v1{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": api},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())
    except Exception as error:  # noqa: BLE001 - report, never traceback
        return 0, {"detail": str(error)}


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{api}/api/v1{path}", timeout=60) as response:
        return json.loads(response.read().decode())


print("\n-- opt-in status --")
for path in ("/database/console", "/kafka/console"):
    data = get(path)["data"]
    print(f"  {path:<20} enabled={data['enabled']} defaultHost={data.get('defaultHost', '')!r}")
    if not data["enabled"]:
        failures.append(f"{path} is disabled -- restart the backend with the opt-in flags")

TARGET = {
    "host": node_ip,
    "port": int(pg_port),
    "database": "demo",
    "username": "demo",
    "password": "demo-not-a-real-credential",
}

print("\n-- PostgreSQL: what the API reads back --")
queries = [
    ("tables", "select table_name from information_schema.tables "
               "where table_schema = 'public' order by 1"),
    ("row counts", "select 'demo_customers' as t, count(*) from public.demo_customers "
                   "union all select 'demo_orders', count(*) from public.demo_orders "
                   "union all select 'demo_events', count(*) from public.demo_events"),
    ("marker rows", f"select sku, count(*) as n, sum(amount)::numeric(10,2) as total "
                    f"from public.demo_orders where sku = 'SKU-{marker}-01' group by sku"),
    ("orders by status", "select status, count(*) as n, sum(amount)::numeric(10,2) as total "
                         "from public.demo_orders group by status order by n desc"),
]
for label, sql in queries:
    status, body = post("/database/query", {**TARGET, "sql": sql})
    data = body.get("data") or {}
    print(f"  [{status}] {label}: rows={data.get('rowCount')} in {body.get('durationMs', '?')}ms")
    if not data:
        failures.append(f"database/{label}: {body.get('detail', body)}")
        continue
    for row in data.get("rows", [])[:6]:
        print(f"        {row}")

print("\n-- PostgreSQL: the write path is still blocked --")
for sql in (
    "drop table public.demo_orders",
    "update public.demo_orders set amount = 0",
    "select 1; delete from public.demo_orders",
):
    status, body = post("/database/query", {**TARGET, "sql": sql})
    detail = str(body.get("detail", ""))
    print(f"  [{status}] {sql[:52]:<52} -> {detail[:58]}")
    if status == 200:
        failures.append(f"read-only guard let this through: {sql}")

print("\n-- Kafka: what the API reads back --")
status, body = post("/kafka/topics", {"host": node_ip, "port": int(kafka_port)})
data = body.get("data") or {}
print(f"  [{status}] bootstrap={data.get('bootstrap')} brokers={data.get('brokers')}")
if not data:
    failures.append(f"kafka/topics: {body.get('detail', body)}")
else:
    for topic in data.get("topics", []):
        mark = " <- marker topic" if topic["name"] == marker else ""
        print(f"        {topic['name']:<22} partitions={topic['partitions']}"
              f" internal={topic['internal']}{mark}")
    if not any(topic["name"] == marker for topic in data.get("topics", [])):
        failures.append(f"marker topic {marker} was not listed by the broker")

print("\n-- Kafka: an unreachable broker is reported, never hidden --")
status, body = post("/kafka/topics", {"host": node_ip, "port": 39999})
print(f"  [{status}] {str(body.get('detail', ''))[:70]}")
if status == 200:
    failures.append("an unreachable broker returned 200")

print("\n== RESULT ==")
if failures:
    for item in failures:
        print(f"  FAIL  {item}")
    sys.exit(1)
print("  PASS  database reads, the read-only guard and Kafka topic listing all verified")
PY
STATUS=$?

if [[ $STATUS -ne 0 ]]; then
    printf '\nlive-smoke: FAILED\n'
    exit $STATUS
fi
printf '\nlive-smoke: PASSED\n'
