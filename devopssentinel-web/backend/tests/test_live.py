"""Opt-in live-data tests: SQL validation + Kafka Metadata parsing.

No database or broker is required -- the allowlist, the target validation and
the Kafka wire parsing are all pure functions.
"""

from __future__ import annotations

import struct

import pytest

from app.services import kafkatool, sqltool


def _stub_node_address(monkeypatch, value: str = "10.0.0.7") -> None:
    """Keep the console status probes hermetic: never spawn kubectl in tests."""
    from app.services import kube

    async def fake(context: str = "") -> str:
        return value

    monkeypatch.setattr(kube, "node_address", fake)


# --------------------------------------------------------------------------
# SQL allowlist
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT * FROM information_schema.tables",
        "with t as (select 1 as a) select * from t",
        "show server_version",
        "explain select 1",
        "table pg_class",
        "values (1)",
        "\\dt",
        "select 'delete me' as harmless",
        "select 1;",
    ],
)
def test_validate_sql_allows_read_only(sql):
    assert sqltool.validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "delete from users",
        "update users set admin = true",
        "insert into users values (1)",
        "drop table users",
        "alter table users add column x int",
        "truncate users",
        "grant all on users to public",
        "copy users to stdout",
        "select 1; drop table users",
        "select 1; select 2",
        "set session authorization bob",
        "begin",
        "call do_thing()",
        "vacuum full",
    ],
)
def test_validate_sql_rejects_everything_else(sql):
    with pytest.raises(sqltool.SqlError):
        sqltool.validate_sql(sql)


def test_validate_sql_rejects_oversized_statements():
    with pytest.raises(sqltool.SqlError):
        sqltool.validate_sql("select '" + "x" * 5000 + "'")


def test_validate_sql_is_case_insensitive():
    with pytest.raises(sqltool.SqlError):
        sqltool.validate_sql("DELETE FROM users")


@pytest.mark.parametrize(
    ("host", "port", "database", "username"),
    [
        ("", 5432, "db", "user"),
        ("-oops", 5432, "db", "user"),
        ("ok.local", 0, "db", "user"),
        ("ok.local", 70000, "db", "user"),
        ("ok.local", 5432, "", "user"),
        ("ok.local", 5432, "db", ""),
        ("ok.local", 5432, "bad name", "user"),
    ],
)
def test_validate_target_rejects_bad_input(host, port, database, username):
    with pytest.raises(sqltool.SqlError):
        sqltool.validate_target(host, port, database, username)


def test_validate_target_accepts_a_realistic_target():
    sqltool.validate_target("172.18.0.2", 30432, "platform", "platform")


def test_database_query_is_disabled_by_default(client, monkeypatch):
    """The console must be inert unless the operator opts in."""
    _stub_node_address(monkeypatch)
    status = client.get("/api/v1/database/console").json()
    assert status["data"]["enabled"] is False
    assert status["status"] == "UNAVAILABLE"
    # The feature is now switched on from the Settings page, so the reason has
    # to point there; the environment variable is only the start-up default.
    assert "Settings" in status["data"]["reason"]
    # The prefill host is the node a NodePort endpoint answers on, not 127.0.0.1.
    assert status["data"]["defaultHost"] == "10.0.0.7"

    response = client.post(
        "/api/v1/database/query",
        json={
            "host": "127.0.0.1",
            "port": 5432,
            "database": "platform",
            "username": "platform",
            "password": "x",
            "sql": "select 1",
        },
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 403


def test_kafka_topics_is_disabled_by_default(client, monkeypatch):
    _stub_node_address(monkeypatch)
    status = client.get("/api/v1/kafka/console").json()
    assert status["data"]["enabled"] is False
    assert "Settings" in status["data"]["reason"]
    assert status["data"]["defaultHost"] == "10.0.0.7"

    response = client.post(
        "/api/v1/kafka/topics",
        json={"host": "127.0.0.1", "port": 9092},
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 403


def test_console_prefill_survives_a_cluster_without_a_node_address(client, monkeypatch):
    """A cluster that reports nothing must not break the status probe."""
    _stub_node_address(monkeypatch, "")
    status = client.get("/api/v1/database/console").json()
    assert status["data"]["defaultHost"] == ""
    assert status["status"] == "UNAVAILABLE"  # still only gated by the opt-in flag


# --------------------------------------------------------------------------
# Runtime toggles (services/liveconfig.py)
# --------------------------------------------------------------------------

def test_env_flag_is_the_startup_default(state_dir, monkeypatch):
    """DSWEB_ENABLE_SQL_CONSOLE=1 still turns the console on at start-up."""
    from app.config import settings
    from app.services import liveconfig

    monkeypatch.setattr(settings, "enable_sql_console", True)
    assert liveconfig.sql_console_enabled() is True


def test_settings_toggle_overrides_the_env_default(state_dir, monkeypatch):
    """A choice made in Settings must win over the start-up environment."""
    from app.config import settings
    from app.services import liveconfig

    monkeypatch.setattr(settings, "enable_sql_console", True)
    monkeypatch.setattr(settings, "enable_kafka_topics", True)

    flags = liveconfig.set_flags(sql_console=False)
    assert flags == {"sqlConsole": False, "kafkaTopics": True}
    assert liveconfig.sql_console_enabled() is False
    # Untouched flags keep following the environment.
    assert liveconfig.kafka_topics_enabled() is True


def test_set_flags_is_private_and_persisted(state_dir):
    from app.services import liveconfig

    liveconfig.set_flags(kafka_topics=True)
    stored = state_dir / "live.json"
    assert stored.is_file()
    assert liveconfig.kafka_topics_enabled() is True
    # 0o600 where the platform honours it; the write must not raise regardless.
    assert liveconfig.snapshot() == {"sqlConsole": False, "kafkaTopics": True}


def test_corrupt_flag_file_falls_back_to_the_environment(state_dir, monkeypatch):
    """A half-written file must never take the server down."""
    from app.config import settings
    from app.services import liveconfig

    monkeypatch.setattr(settings, "enable_sql_console", True)
    (state_dir / "live.json").write_text("{ not json", encoding="utf-8")
    assert liveconfig.sql_console_enabled() is True


# --------------------------------------------------------------------------
# Kafka Metadata (v1) response parsing
# --------------------------------------------------------------------------

def _string(value: str) -> bytes:
    raw = value.encode()
    return struct.pack(">h", len(raw)) + raw


def _partition(index: int, leader: int = 1) -> bytes:
    body = struct.pack(">hii", 0, index, leader)
    body += struct.pack(">i", 1) + struct.pack(">i", 1)  # replicas
    body += struct.pack(">i", 1) + struct.pack(">i", 1)  # in-sync replicas
    return body


def _kafka_metadata_response() -> bytes:
    """A Metadata v1 response: one broker, two listable topics, one error."""
    body = struct.pack(">i", 1)  # correlation id
    body += struct.pack(">i", 1)  # one broker
    body += struct.pack(">i", 1) + _string("kafka.default.svc") + struct.pack(">i", 9092)
    body += struct.pack(">h", -1)  # rack = null (v1 only)
    body += struct.pack(">i", 1)  # controller id (v1 only)
    body += struct.pack(">i", 3)  # three topics
    # orders: healthy, two partitions, user topic
    body += struct.pack(">h", 0) + _string("orders") + struct.pack(">?i", False, 2)
    body += _partition(0) + _partition(1)
    # __consumer_offsets: internal flag set by the broker
    body += struct.pack(">h", 0) + _string("__consumer_offsets") + struct.pack(">?i", True, 1)
    body += _partition(0)
    # hidden: broker-side error -> skipped
    body += struct.pack(">h", 5) + _string("hidden") + struct.pack(">?i", False, 0)
    return body


def test_parse_kafka_metadata_lists_topics_and_brokers():
    listing = kafkatool._parse(_kafka_metadata_response())
    assert listing.brokers == ["1:kafka.default.svc:9092"]
    by_name = {topic.name: topic for topic in listing.topics}
    # The errored topic is skipped, the rest are sorted.
    assert [topic.name for topic in listing.topics] == ["__consumer_offsets", "orders"]
    assert by_name["orders"].partitions == 2
    assert by_name["orders"].internal is False
    assert by_name["__consumer_offsets"].internal is True


def test_kafka_request_is_a_single_metadata_v1_call():
    """Kafka 3.9 removed Metadata v0, so the adapter must ask for v1."""
    request = kafkatool._request(7)
    size = struct.unpack(">i", request[:4])[0]
    assert size == len(request) - 4
    api_key, api_version, correlation_id = struct.unpack(">hhi", request[4:12])
    assert (api_key, api_version, correlation_id) == (3, 1, 7)
    assert struct.unpack(">i", request[-4:])[0] == -1  # -1 = every topic


@pytest.mark.parametrize(
    ("host", "port"),
    [("", 9092), ("has space", 9092), ("ok.local", 0), ("ok.local", 99999)],
)
def test_kafka_target_validation(host, port):
    with pytest.raises(kafkatool.KafkaError):
        kafkatool.validate_target(host, port)
