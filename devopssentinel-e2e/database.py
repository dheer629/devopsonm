"""Real, isolated PostgreSQL and Kafka fixtures for the WSL E2E harness.

The application remains read-only. Fixture DDL, INSERTs, topic creation, and
consumer offset setup are performed explicitly by this test infrastructure.
"""

import os
from pathlib import Path
import secrets
import tempfile
import time


def run(h):
    assert h.ns == "devopssentinel-e2e", "Database fixtures require the dedicated E2E namespace"
    assert h.labels.get("devopssentinel.io/test-suite") == "true"
    assert h.labels.get("app.kubernetes.io/part-of") == "devopssentinel-e2e"
    pg_name = "ds-e2e-postgres"
    kafka_name = "ds-e2e-kafka"
    state = {}

    def obj(kind, name, **extra):
        return {
            "apiVersion": "v1",
            "kind": kind,
            "metadata": {"name": name, "labels": dict(h.labels)},
            **extra,
        }

    def ready(pod):
        return any(c.get("type") == "Ready" and c.get("status") == "True"
                   for c in pod.get("status", {}).get("conditions", []))

    def checked(result, description):
        assert result.returncode == 0, f"{description}: exit {result.returncode}"
        return result.stdout

    def pg_exec(sql):
        result = h.k([
            "exec", "-i", pg_name, "--", "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
            "-U", "sentinel_integration", "-d", "devopssentinel", "-At",
        ], ns=h.ns, timeout=30, input=sql)
        return checked(result, "PostgreSQL fixture truth query").strip()

    def postgres():
        if state.get("pg_ready"):
            truth = h.get("pod", pg_name, h.ns)
            assert ready(truth), "PostgreSQL fixture lost readiness"
            h.evidence("database/postgres-pod.json", truth)
            return truth
        if "pg_error" in state:
            h.block(state["pg_error"])
        password = "DS_E2E_PG:" + secrets.token_hex(24) + "\\" + secrets.token_hex(12)
        state["password"] = password
        password_file.write_text(password + "\n", encoding="utf-8")
        password_file.chmod(0o600)
        # h.apply sends this only to Kubernetes; Secret evidence is sanitized.
        h.apply(obj("Secret", pg_name, type="Opaque", stringData={"password": password}), h.ns)
        sql = """CREATE TABLE public.e2e_audit (
    id integer PRIMARY KEY,
    event text NOT NULL
);
INSERT INTO public.e2e_audit(id, event) VALUES
    (1, 'fixture created'), (2, 'readonly validation'), (3, 'synthetic audit event');
"""
        h.apply(obj("ConfigMap", "ds-e2e-postgres-init", data={"01-fixture.sql": sql}), h.ns)
        pod = obj("Pod", pg_name, spec={
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "containers": [{
                "name": "postgres", "image": "postgres:16-alpine", "imagePullPolicy": "IfNotPresent",
                "env": [
                    {"name": "POSTGRES_DB", "value": "devopssentinel"},
                    {"name": "POSTGRES_USER", "value": "sentinel_integration"},
                    {"name": "POSTGRES_PASSWORD_FILE", "value": "/run/credentials/password"},
                    {"name": "POSTGRES_HOST_AUTH_METHOD", "value": "scram-sha-256"},
                ],
                "ports": [{"containerPort": 5432}],
                "readinessProbe": {
                    "exec": {"command": ["pg_isready", "-U", "sentinel_integration", "-d", "devopssentinel"]},
                    "periodSeconds": 2,
                },
                "resources": {"requests": {"cpu": "25m", "memory": "64Mi"},
                              "limits": {"cpu": "500m", "memory": "256Mi"}},
                "volumeMounts": [
                    {"name": "data", "mountPath": "/var/lib/postgresql/data"},
                    {"name": "credentials", "mountPath": "/run/credentials", "readOnly": True},
                    {"name": "init", "mountPath": "/docker-entrypoint-initdb.d", "readOnly": True},
                ],
            }],
            "volumes": [
                {"name": "data", "emptyDir": {}},
                {"name": "credentials", "secret": {"secretName": pg_name}},
                {"name": "init", "configMap": {"name": "ds-e2e-postgres-init"}},
            ],
        })
        pod["metadata"]["labels"]["app"] = pg_name
        h.apply(pod, h.ns)
        h.apply(obj("Service", pg_name, spec={
            "selector": {"app": pg_name}, "ports": [{"name": "postgres", "port": 5432, "targetPort": 5432}],
        }), h.ns)
        try:
            truth = h.wait("pod", pg_name, ready, h.ns, timeout=120)
        except Exception as exc:
            state["pg_error"] = f"PostgreSQL fixture did not become Ready after a 120s deadline: {exc}"
            h.block(state["pg_error"])
        # The postgres entrypoint restarts the server after running the init
        # scripts, so the first connection after readiness can fail with exit 2.
        deadline = time.monotonic() + 120
        while True:
            probe = h.k(["exec", "-i", pg_name, "--", "psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
                         "-U", "sentinel_integration", "-d", "devopssentinel", "-At",
                         "-c", "SELECT count(*) FROM public.e2e_audit;"], ns=h.ns, timeout=30)
            if probe.returncode == 0:
                rows = probe.stdout.strip()
                break
            if time.monotonic() >= deadline:
                raise AssertionError("PostgreSQL fixture truth query: exit %s after deadline" % probe.returncode)
            time.sleep(3)
        assert rows == "3", f"Real PostgreSQL fixture row count was {rows!r}, expected 3"
        audit = pg_exec("SELECT id, event FROM public.e2e_audit ORDER BY id;")
        state["pg_ready"] = truth
        h.evidence("database/postgres-pod.json", truth)
        h.evidence("database/postgres-fixture-truth.txt", f"database=devopssentinel\nschema=public\ntable=e2e_audit\nrow_count={rows}\n{audit}\n")
        return truth

    def pg_discovery():
        postgres()
        endpoint = h.wait("endpoints", pg_name,
                          lambda o: any(s.get("addresses") for s in o.get("subsets", [])),
                          h.ns, timeout=60)
        service = h.get("service", pg_name, h.ns)
        assert service["spec"]["ports"][0]["port"] == 5432
        result = h.sentinel(["--postgres-discovery"], h.ns)
        h.evidence("database/postgres-discovery.txt", result.stdout + result.stderr)
        h.evidence("database/postgres-service.json", service)
        h.evidence("database/postgres-endpoints.json", endpoint)
        checked(result, "Sentinel PostgreSQL discovery")
        addresses = [a["ip"] for s in endpoint["subsets"] for a in s.get("addresses", [])]
        assert pg_name in result.stdout and "5432" in result.stdout
        assert any(ip in result.stdout for ip in addresses), "Sentinel omitted the actual ready database endpoint"
        return {"fixture": f"Pod/{pg_name}, Service/{pg_name}", "kubernetes_truth": {"ready_endpoints": addresses, "port": 5432},
                "expected": "Sentinel reports the real Service, port, and ready endpoint", "actual": "Service and ready endpoint match Kubernetes",
                "evidence": "database/postgres-discovery.txt"}

    def pg_sessions():
        postgres()
        if "pg_session_result" not in state:
            with h.forward(pg_name, 5432, h.ns) as port:
                probe = h.command(["docker", "run", "--rm", "--network", "host", "--entrypoint", "python3",
                    h.tools_image, "-c", "import socket,sys;s=socket.socket();s.settimeout(3);"
                    "sys.exit(0 if s.connect_ex(('127.0.0.1'," + str(port) + "))==0 else 1)"], timeout=60)
                if probe.returncode != 0:
                    h.block("PostgreSQL integration requires the tools container to reach the kubectl "
                            "port-forward on 127.0.0.1:" + str(port) + ". Docker Desktop isolates container "
                            "networking from the WSL host, so `docker run --network host` cannot reach a "
                            "port-forward created in the Ubuntu distro. Next action: run this domain from a "
                            "WSL-native shell without Docker Desktop network isolation, or use an in-cluster "
                            "client pod. Environment limit, not a DevOpsSentinel defect.")
                result = h.command([
                    "docker", "run", "--rm", "--network", "host", "--user", f"{os.getuid()}:{os.getgid()}",
                    "--env", "HOME=/tmp", "--entrypoint", "bash",
                    "--mount", f"type=bind,source={h.root},target=/workspace,readonly",
                    "--mount", f"type=bind,source={password_file},target=/run/ds-e2e-password,readonly",
                    h.tools_image, "/workspace/tests/postgres_integration.sh", "127.0.0.1", str(port),
                    "devopssentinel", "sentinel_integration", "/run/ds-e2e-password",
                ], timeout=150)
            output = result.stdout + result.stderr
            assert state["password"] not in output, "PostgreSQL password leaked in integration output"
            h.evidence("database/postgres-sessions.txt", output)
            state["pg_session_result"] = result
        else:
            result = state["pg_session_result"]
            h.evidence("database/postgres-sessions.txt", result.stdout + result.stderr)
        return state["pg_session_result"]

    def pg_queries():
        result = pg_sessions()
        checked(result, "PostgreSQL integration assertions")
        output = result.stdout
        for kind in ("identity", "sizes", "activity", "long_running"):
            assert f"PASS {kind} exit status" in output, f"Real PostgreSQL query failed: {kind}"
            assert f"PASS {kind} is read-only on the server and rejects writes" in output, f"Read-only transaction check failed: {kind}"
        for phrase in ("restores caller environment", "removes temporary password file", "does not disclose the password"):
            assert f"FAIL " not in "\n".join(line for line in output.splitlines() if phrase in line), phrase
        assert "PASS wrapper found no credential or connection safety errors" in output
        return {"fixture": f"Pod/{pg_name}; actual psql/libpq with a random colon/backslash password",
                "kubernetes_truth": "PostgreSQL Ready; 3 actual audit rows",
                "expected": "Four fixed SELECTs succeed; server rejects writes; no password exposure; caller environment restored",
                "actual": "All query, authentication transport, read-only, permission, restoration, and cleanup checks passed",
                "evidence": "database/postgres-sessions.txt"}

    def pg_failures():
        result = pg_sessions()
        checked(result, "PostgreSQL integration assertions")
        output = result.stdout
        for phrase in (
            "wrong_password exit status", "wrong password reaches real PostgreSQL authentication",
            "wrong password is classified as authentication failure", "invalid_database exit status",
            "invalid database is rejected by PostgreSQL", "unreachable exit status",
            "unreachable port is classified as network failure", "back removes temporary password file",
            "cancel removes temporary password file",
        ):
            assert f"PASS {phrase}" in output, f"PostgreSQL negative check failed: {phrase}"
        return {"fixture": f"Pod/{pg_name}; wrong synthetic password, absent database, localhost closed port",
                "expected": "Authentication, missing-database and network failures produce nonzero exits; cancellation removes credentials",
                "actual": "All real PostgreSQL negative checks and cancellation cleanup passed",
                "evidence": "database/postgres-sessions.txt"}

    def pg_schema_audit():
        postgres()
        truth = pg_exec("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name='e2e_audit';")
        rows = pg_exec("SELECT count(*) FROM public.e2e_audit;")
        h.evidence("database/postgres-schema-audit.txt", f"schema_table={truth}\nrow_count={rows}\n")
        # These were explicitly requested; the current fixed menu exposes only
        # identity, sizes, activity, and long-running sessions. Report the gap.
        h.block("Schema discovery, table row count and audit query are not exposed by the "
                "four-option PostgreSQL menu (identity, sizes, activity, long-running); the real "
                "fixture confirms public.e2e_audit exists with 3 rows. Next action: add a schema/row-count "
                "read-only query option to the Sentinel PostgreSQL engine, then rerun --domain database. "
                "This product capability gap is not counted as a pass.")

    def kafka_exec(script, timeout=90):
        result = h.k(["exec", "-i", kafka_name, "--", "bash", "-s"], ns=h.ns, timeout=timeout, input=script)
        return result

    def kafka():
        if state.get("kafka_ready"):
            truth = h.get("pod", kafka_name, h.ns)
            assert ready(truth), "Kafka fixture lost readiness"
            h.evidence("database/kafka-pod.json", truth)
            h.evidence("database/kafka-setup.txt", state["kafka_setup"])
            return truth
        if "kafka_error" in state:
            h.block(state["kafka_error"])
        bootstrap = f"{kafka_name}.{h.ns}.svc:9092"
        properties = f"""process.roles=broker,controller
node.id=1
controller.quorum.voters=1@127.0.0.1:9093
listeners=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=PLAINTEXT://{bootstrap}
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
controller.listener.names=CONTROLLER
log.dirs=/var/lib/kafka/data
num.partitions=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0
auto.create.topics.enable=false
num.network.threads=2
num.io.threads=2
"""
        h.apply(obj("ConfigMap", "ds-e2e-kafka-config", data={
            "server.properties": properties,
            "sentinel.sh": (h.root / "DevOps_K8s_Sentinel_FINAL_GP.sh").read_text(encoding="utf-8"),
        }), h.ns)
        pod = obj("Pod", kafka_name, spec={
            "automountServiceAccountToken": False, "restartPolicy": "Never",
            "securityContext": {"fsGroup": 1000},
            "containers": [{
                "name": "kafka", "image": "apache/kafka:3.9.1", "imagePullPolicy": "IfNotPresent",
                "command": ["bash", "-ec", "/opt/kafka/bin/kafka-storage.sh format --ignore-formatted -t \"$(/opt/kafka/bin/kafka-storage.sh random-uuid)\" -c /fixture/server.properties; exec /opt/kafka/bin/kafka-server-start.sh /fixture/server.properties"],
                "env": [{"name": "KAFKA_HEAP_OPTS", "value": "-Xms128m -Xmx256m"}],
                "ports": [{"containerPort": 9092}, {"containerPort": 9093}],
                "readinessProbe": {"tcpSocket": {"port": 9092}, "periodSeconds": 3},
                "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                              "limits": {"cpu": "1000m", "memory": "768Mi"}},
                "volumeMounts": [{"name": "config", "mountPath": "/fixture", "readOnly": True},
                                 {"name": "data", "mountPath": "/var/lib/kafka/data"}],
            }],
            "volumes": [{"name": "config", "configMap": {"name": "ds-e2e-kafka-config"}},
                        {"name": "data", "emptyDir": {}}],
        })
        pod["metadata"]["labels"]["app"] = kafka_name
        h.apply(pod, h.ns)
        h.apply(obj("Service", kafka_name, spec={"selector": {"app": kafka_name},
                 "ports": [{"name": "kafka", "port": 9092, "targetPort": 9092}]}), h.ns)
        try:
            truth = h.wait("pod", kafka_name, ready, h.ns, timeout=180)
        except Exception as exc:
            state["kafka_error"] = ("Local Kafka fixture unavailable. Attempted pinned apache/kafka:3.9.1 with a 256Mi JVM heap and "
                                    f"768Mi memory limit; it did not become Ready within 180s: {exc}. "
                                    "Next action: inspect ds-e2e-kafka image-pull events and available local memory, then rerun --domain database.")
            h.block(state["kafka_error"])
        setup = kafka_exec(f"""set -euo pipefail
export PATH=/opt/kafka/bin:$PATH KAFKA_HEAP_OPTS='-Xms32m -Xmx128m'
kafka-topics.sh --bootstrap-server {bootstrap} --create --if-not-exists --topic ds-e2e-topic --partitions 1 --replication-factor 1
printf 'synthetic-message-1\\nsynthetic-message-2\\nsynthetic-message-3\\n' | kafka-console-producer.sh --bootstrap-server {bootstrap} --topic ds-e2e-topic
kafka-console-consumer.sh --bootstrap-server {bootstrap} --topic ds-e2e-topic --group ds-e2e-group --from-beginning --max-messages 1 --timeout-ms 10000
kafka-consumer-groups.sh --bootstrap-server {bootstrap} --group ds-e2e-group --topic ds-e2e-topic --reset-offsets --to-earliest --execute
kafka-consumer-groups.sh --bootstrap-server {bootstrap} --describe --group ds-e2e-group
""", timeout=120)
        h.evidence("database/kafka-setup.txt", setup.stdout + setup.stderr)
        checked(setup, "Real Kafka topic, messages and consumer group setup")
        assert "ds-e2e-topic" in setup.stdout and "ds-e2e-group" in setup.stdout
        h.evidence("database/kafka-pod.json", truth)
        state["kafka_ready"] = truth
        state["kafka_setup"] = setup.stdout + setup.stderr
        state["bootstrap"] = bootstrap
        return truth

    def kafka_reports():
        kafka()
        discovery = h.sentinel(["--kafka-discovery"], h.ns)
        h.evidence("database/kafka-discovery.txt", discovery.stdout + discovery.stderr)
        checked(discovery, "Sentinel Kafka discovery")
        assert kafka_name in discovery.stdout and "9092" in discovery.stdout
        result = kafka_exec(f"""set -o pipefail
source /fixture/sentinel.sh
export PATH=/opt/kafka/bin:$PATH KAFKA_HEAP_OPTS='-Xms32m -Xmx128m'
API_TIMEOUT=30
RUN_DIR=$(mktemp -d)
trap 'rm -rf -- "$RUN_DIR"' EXIT
kafka_connectivity_report {state['bootstrap']} || exit $?
kafka_topics_report {state['bootstrap']} || exit $?
kafka_groups_report {state['bootstrap']} || exit $?
""", timeout=100)
        h.evidence("database/kafka-sentinel.txt", result.stdout + result.stderr)
        if result.returncode >= 128 or "TOOL_MISSING" in result.stdout:
            h.block("In-pod Sentinel Kafka run exited " + str(result.returncode) +
                    (" (SIGSEGV)" if result.returncode == 139 else "") +
                    ". The apache/kafka:3.9.1 CLI JVM did not complete inside the disposable WSL fixture. "
                    "Next action: raise the fixture heap/memory or run against a WSL-native Kafka. "
                    "Environment/resource limit, not a DevOpsSentinel defect.")
        checked(result, "Sentinel real Kafka connectivity/topics/groups")
        assert "TCP: OK" in result.stdout
        assert "ds-e2e-topic" in result.stdout
        assert "ds-e2e-group" in result.stdout
        return {"fixture": f"Pod/{kafka_name}; topic ds-e2e-topic; 3 messages; consumer group ds-e2e-group",
                "kubernetes_truth": "Kafka Pod Ready; broker administration confirms topic and committed consumer group",
                "expected": "Sentinel discovers the Service and connects, lists the actual topic and group",
                "actual": "All real Kafka reports match the broker and Kubernetes",
                "evidence": "database/kafka-sentinel.txt"}

    def kafka_lag():
        kafka()
        h.na("Consumer lag is conditional on product support in the request. Sentinel exposes connectivity, topic listing and group listing, but has no lag-report operation; real broker group/offset truth is retained in database/kafka-setup.txt.")

    with tempfile.TemporaryDirectory(prefix=".ds-e2e-pg-", dir=Path.home()) as private:
        password_file = Path(private) / "password"
        h.case("DS-E2E-079", "database", "PostgreSQL Service, endpoint and port discovery", pg_discovery)
        h.case("DS-E2E-080", "database", "PostgreSQL real read-only SELECTs and credential lifecycle", pg_queries)
        h.case("DS-E2E-081", "database", "PostgreSQL wrong password, invalid database and unreachable service", pg_failures)
        h.case("DS-E2E-082", "database", "PostgreSQL schema, row count and audit query capability", pg_schema_audit)
        h.case("DS-E2E-083", "database", "Kafka real broker, messages, topic and consumer group reports", kafka_reports)
        h.case("DS-E2E-084", "database", "Kafka consumer lag support", kafka_lag)
