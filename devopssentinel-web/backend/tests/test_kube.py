"""Read-only kubectl discovery guard tests."""

from __future__ import annotations

import pytest

from app.services.kube import (
    KubeError,
    _validate,
    parse_cpu,
    parse_memory,
    parse_node_address,
    parse_top_nodes,
    parse_top_pods,
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
        "demo-kafka-54c877b698-ds669   3m      364Mi\n"
        "demo-postgres-69b874798-hr8nh  12m     18Mi\n"
        "demo-web-75899ccfd7-ckpcg      0       11Mi\n"
    )
    rows = parse_top_pods(output)
    assert [row["name"] for row in rows] == [
        "demo-kafka-54c877b698-ds669",
        "demo-postgres-69b874798-hr8nh",
        "demo-web-75899ccfd7-ckpcg",
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
