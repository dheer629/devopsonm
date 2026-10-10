"""Read-only kubectl discovery guard tests."""

from __future__ import annotations

import asyncio

import pytest

from app.services.kube import (
    KubeError,
    _validate,
    command_string,
    describe_argv,
    events_argv,
    logs_argv,
    namespace_events,
    parse_cpu,
    parse_memory,
    parse_node_address,
    parse_top_nodes,
    parse_top_pods,
    pod_containers,
)


def test_allows_the_read_only_discovery_calls():
    _validate(["config", "get-contexts", "-o", "name"])
    _validate(["config", "current-context"])
    _validate(["get", "namespaces"])
    _validate(["get", "ns"])
    # The node InternalIP that a NodePort live-data endpoint sits on.
    _validate(["get", "nodes", "-o", "jsonpath={.items[0].status.addresses[0].address}"])
    # Resource usage is read-only too, and needed for the usage charts.
    _validate(["top", "pods", "--no-headers"])
    _validate(["top", "nodes", "--no-headers"])
    _validate(["--context", "c", "--namespace", "default", "top", "pods", "--no-headers"])


def test_allows_global_flags_before_the_verb():
    """Regression: `--context X get namespaces` must be accepted."""
    _validate(["--context", "kubernetes-super-admin@dev", "get", "namespaces", "-o", "name"])
    _validate(["--kubeconfig", "/tmp/k", "--context", "c", "get", "namespaces"])


def test_blocks_mutation_verbs():
    for bad in (
        ["delete", "pod", "x"],
        ["apply", "-f", "x.yaml"],
        ["--context", "c", "delete", "namespaces", "x"],
        ["exec", "-it", "pod", "--", "sh"],
        ["--context", "c", "get", "secrets"],
        ["top", "pods", "delete", "pod/x"],
        ["--context", "c", "top", "secrets"],
    ):
        with pytest.raises((KubeError, PermissionError)):
            _validate(bad)


# --------------------------------------------------------------------------
# `kubectl top` parsing
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "cores"),
    [
        ("0", 0.0),
        ("250m", 0.25),
        ("1000m", 1.0),
        ("2", 2.0),
        ("1500u", 0.0015),
        ("1500000000n", 1.5),
        ("<unknown>", 0.0),
        ("", 0.0),
        ("garbage", 0.0),
    ],
)
def test_parse_cpu(raw, cores):
    assert parse_cpu(raw) == pytest.approx(cores)


@pytest.mark.parametrize(
    ("raw", "byte_count"),
    [
        ("364Mi", 364 * 1024**2),
        ("1Gi", 1024**3),
        ("512Ki", 512 * 1024),
        ("1500K", 1_500_000),
        ("12345", 12345),
        ("<unknown>", 0),
        ("", 0),
        ("nonsense", 0),
    ],
)
def test_parse_memory(raw, byte_count):
    assert parse_memory(raw) == byte_count


def test_parse_top_pods_reads_the_kubectl_columns():
    output = (
        "platform-kafka-54c877b698-ds669   3m      364Mi\n"
        "platform-postgres-69b874798-hr8nh  12m     18Mi\n"
        "platform-web-75899ccfd7-ckpcg      0       11Mi\n"
    )
    rows = parse_top_pods(output)
    assert [row["name"] for row in rows] == [
        "platform-kafka-54c877b698-ds669",
        "platform-postgres-69b874798-hr8nh",
        "platform-web-75899ccfd7-ckpcg",
    ]
    assert rows[0]["cpuMillicores"] == 3
    assert rows[0]["memoryBytes"] == 364 * 1024**2
    assert rows[2]["cpuMillicores"] == 0


def test_parse_top_nodes_reads_percentages():
    output = "dev   140m   0%   1850Mi   24%\n"
    rows = parse_top_nodes(output)
    assert len(rows) == 1
    assert rows[0]["name"] == "dev"
    assert rows[0]["cpuPercent"] == 0.0
    assert rows[0]["memoryPercent"] == 24.0
    assert rows[0]["memoryBytes"] == 1850 * 1024**2


def test_parse_top_ignores_malformed_lines():
    assert parse_top_pods("") == []
    assert parse_top_pods("only-a-name\n") == []
    assert parse_top_nodes("dev 140m\n") == []


# --------------------------------------------------------------------------
# Node address (the host a NodePort live-data endpoint answers on)
# --------------------------------------------------------------------------

def test_parse_node_address_reads_the_jsonpath_output():
    assert parse_node_address("172.18.0.2") == "172.18.0.2"
    assert parse_node_address("  10.0.0.7  \n") == "10.0.0.7"
    # jsonpath prints nothing at all when no node advertises an InternalIP.
    assert parse_node_address("") == ""
    assert parse_node_address("\n  \n") == ""


def test_node_address_cannot_be_turned_into_a_mutation():
    """`get nodes` is allowed; the read-only guard still blocks everything else."""
    _validate(["get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"])
    for bad in (
        ["get", "nodes", "--show-labels", "delete", "node/dev"],
        ["get", "node", "dev"],
        ["get", "secrets"],
    ):
        with pytest.raises((KubeError, PermissionError)):
            _validate(bad)


# --------------------------------------------------------------------------
# Log viewer allowlist + argv
# --------------------------------------------------------------------------

def test_allows_logs_with_the_viewer_option_surface():
    _validate(["logs", "platform-web-abc"])
    _validate(["logs", "platform-web-abc", "-c", "web", "--tail=500"])
    _validate(
        [
            "--context", "c", "--namespace", "default",
            "logs", "platform-web-abc", "-c", "web",
            "--tail=1000", "--since=30m", "--previous=true", "--timestamps=true",
        ]
    )


def test_blocks_disallowed_logs_flags():
    for bad in (
        ["logs"],
        ["logs", "platform-web-abc", "--follow"],
        ["logs", "platform-web-abc", "--tail=abc"],
        ["logs", "platform-web-abc", "--since=1d"],
        ["logs", "platform-web-abc", "-c", "Bad_Name"],
        ["logs", "platform-web-abc", "--tail"],
        ["logs", "platform-web-abc", "extra-positional"],
    ):
        with pytest.raises(KubeError):
            _validate(bad)


def test_logs_argv_is_read_only_and_bounded():
    argv = logs_argv(
        "platform-web-abc",
        context="c",
        namespace="default",
        container="web",
        tail=1000,
        since="30m",
        previous=True,
        timestamps=True,
    )
    assert argv[:2] == ["--context", "c"]
    assert "--namespace" in argv and "default" in argv
    assert argv[-6:] == [
        "logs", "platform-web-abc", "-c", "web", "--tail=1000",
        "--since=30m",
    ] or argv[-8:] == [
        "logs", "platform-web-abc", "-c", "web", "--tail=1000",
        "--since=30m", "--previous=true", "--timestamps=true",
    ]
    assert argv[-2:] == ["--previous=true", "--timestamps=true"]


def test_logs_argv_omits_since_when_empty():
    argv = logs_argv("pod-x", namespace="default")
    assert argv == ["--namespace", "default", "logs", "pod-x", "--tail=500",
                    "--timestamps=true"]


# --------------------------------------------------------------------------
# Resource description allowlist + argv
# --------------------------------------------------------------------------

def test_allows_describe_and_get_for_non_secret_kinds():
    _validate(["describe", "Deployment", "platform-web"])
    _validate(["get", "deployment", "platform-web", "-o", "yaml"])
    _validate(["--context", "c", "--namespace", "default", "get", "pod", "p", "-o", "json"])
    _validate(["get", "events", "-o", "json"])


def test_blocks_secret_and_unknown_describe_targets():
    for bad in (
        ["describe", "Secret", "platform-tls"],
        ["get", "secret", "platform-tls", "-o", "yaml"],
        ["get", "secrets"],
        ["describe", "Deployment"],  # missing name
        ["get", "deployment", "platform-web", "-o", "wide"],
        ["describe", "Deployment", "platform-web", "extra"],
        ["get", "events", "--field-selector", "x=y"],
    ):
        with pytest.raises((KubeError, PermissionError)):
            _validate(bad)


def test_describe_argv_formats():
    assert describe_argv("Deployment", "web", fmt="describe")[-3:] == [
        "describe", "Deployment", "web",
    ]
    assert describe_argv("Deployment", "web", fmt="yaml")[-5:] == [
        "get", "Deployment", "web", "-o", "yaml",
    ]
    with pytest.raises(KubeError):
        describe_argv("Deployment", "web", fmt="wide")


def test_events_argv_shape():
    assert events_argv(context="c", namespace="default") == [
        "--context", "c", "--namespace", "default", "get", "events", "-o", "json",
    ]


def test_command_string_quotes_arguments():
    assert command_string(["logs", "pod", "--tail=500"]) == "kubectl logs pod --tail=500"


# --------------------------------------------------------------------------
# pod_containers / namespace_events JSON parsing (kubectl mocked)
# --------------------------------------------------------------------------

def _stub_run(monkeypatch, out: str, rc: int = 0, err: str = "") -> None:
    from app.services import kube

    async def fake(args, timeout: float = 15.0):
        return rc, out, err

    monkeypatch.setattr(kube, "_run", fake)


def test_pod_containers_reads_init_app_and_ephemeral(monkeypatch):
    payload = (
        '{"spec":{"initContainers":[{"name":"init"}],'
        '"containers":[{"name":"web"},{"name":"sidecar"}],'
        '"ephemeralContainers":[{"name":"debugger"}]}}'
    )
    _stub_run(monkeypatch, payload)
    assert asyncio.run(pod_containers("pod-x")) == ["init", "web", "sidecar", "debugger"]


def test_pod_containers_survives_non_json(monkeypatch):
    _stub_run(monkeypatch, "not json")
    assert asyncio.run(pod_containers("pod-x")) == []


def test_namespace_events_filters_by_involved_object(monkeypatch):
    payload = (
        '{"items":['
        '{"lastTimestamp":"2026-10-03T00:00:00Z","type":"Warning","reason":"BackOff",'
        '"count":3,"message":"back-off","involvedObject":{"kind":"Pod","name":"web"}},'
        '{"lastTimestamp":"2026-10-03T00:01:00Z","type":"Normal","reason":"Pulled",'
        '"involvedObject":{"kind":"Pod","name":"other"}}'
        "]}"
    )
    _stub_run(monkeypatch, payload)
    rows = asyncio.run(namespace_events(namespace="default", name="web"))
    assert len(rows) == 1
    assert rows[0]["reason"] == "BackOff"
    assert rows[0]["object"] == "Pod/web"
    assert rows[0]["count"] == 3


def test_events_argv_is_cluster_wide_without_a_namespace():
    """No namespace must mean the whole cluster, not just ``default``."""
    assert events_argv(context="c") == [
        "--context", "c", "--all-namespaces", "get", "events", "-o", "json",
    ]
    assert events_argv() == ["--all-namespaces", "get", "events", "-o", "json"]


def test_namespace_events_labels_cluster_wide_rows_with_their_namespace(monkeypatch):
    """Rows from different namespaces must stay distinguishable in one table."""
    payload = (
        '{"items":['
        '{"lastTimestamp":"2026-10-03T00:00:00Z","type":"Warning","reason":"BackOff",'
        '"involvedObject":{"kind":"Pod","name":"web","namespace":"flux-system"}}'
        "]}"
    )
    _stub_run(monkeypatch, payload)
    rows = asyncio.run(namespace_events())
    assert len(rows) == 1
    assert rows[0]["object"] == "flux-system/Pod/web"

