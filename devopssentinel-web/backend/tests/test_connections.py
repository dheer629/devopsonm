"""Cluster-connection manager tests.

Covers the failure that made the Settings page unusable in a container: a port
sweep finds every API server on the Docker host, including ones that answer
``/version`` anonymously and then reject the client certificate with a 401.
That case must be reported as "not your cluster", never as "no kubeconfig".
"""

from __future__ import annotations

import pytest

from app.api import connections as api
from app.services import connections


# --------------------------------------------------------------- reasons


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        # Verbatim from a vcluster reached with another cluster's kubeconfig.
        (
            "error: You must be logged in to the server "
            "(the server has asked for the client to provide credentials)",
            connections.REASON_UNAUTHORIZED,
        ),
        ("error: Unauthorized", connections.REASON_UNAUTHORIZED),
        (
            'pods is forbidden: User "x" cannot list resource "pods"',
            connections.REASON_FORBIDDEN,
        ),
        (
            "The connection to the server localhost:10093 was refused - "
            "did you specify the right host or port?",
            connections.REASON_UNREACHABLE,
        ),
        (
            "Unable to connect to the server: dial tcp 10.0.0.1:6443: i/o timeout",
            connections.REASON_UNREACHABLE,
        ),
        ("x509: certificate signed by unknown authority", connections.REASON_TLS),
        ("context deadline exceeded", connections.REASON_TIMEOUT),
        ("something nobody predicted", connections.REASON_FAILED),
    ],
)
def test_classify_failure_maps_real_kubectl_errors(detail: str, expected: str) -> None:
    assert connections.classify_failure(detail) == expected


def test_classify_failure_treats_empty_input_as_failed() -> None:
    assert connections.classify_failure("") == connections.REASON_FAILED


# ----------------------------------------------------------------- probe


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub_probe(monkeypatch, *, proc: _Proc, seen: list | None = None):
    """Replace kubectl and the rewrite step so probe() runs without a cluster."""

    def fake_materialise(target, **_kwargs):
        if seen is not None:
            seen.append(target)
        target.write_text("apiVersion: v1\n", encoding="utf-8")
        return target

    monkeypatch.setattr(connections, "materialise_to", fake_materialise)
    monkeypatch.setattr(connections, "_kubectl_run", lambda *a, **k: proc)


def test_probe_reports_unauthorized_for_a_foreign_cluster(state_dir, monkeypatch) -> None:
    _stub_probe(
        monkeypatch,
        proc=_Proc(1, stderr="error: You must be logged in to the server (401)"),
    )
    result = connections.probe(
        kubeconfig="/host-kube/config",
        context="vcluster-docker_dev",
        server_override="https://host.docker.internal:10093",
        insecure_skip_tls_verify=True,
    )
    assert result.reachable is False
    assert result.reason == connections.REASON_UNAUTHORIZED
    assert result.status == connections.REASON_UNAUTHORIZED
    assert "logged in" in result.detail


def test_probe_reports_reachable_with_version_and_namespace_count(state_dir, monkeypatch) -> None:
    calls = {"n": 0}

    def two_step(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Proc(0, stdout='{"serverVersion":{"gitVersion":"v1.30.4"}}')
        return _Proc(0, stdout="namespace/default\nnamespace/kube-system\n")

    _stub_probe(monkeypatch, proc=_Proc())
    monkeypatch.setattr(connections, "_kubectl_run", two_step)
    result = connections.probe(kubeconfig="/k", context="c")
    assert result.reachable is True
    assert result.server_version == "v1.30.4"
    assert result.namespace_count == 2
    assert result.reason == ""


def test_probe_uses_a_private_scratch_file(state_dir, monkeypatch) -> None:
    """A shared scratch path is a data race between overlapping probes."""
    seen: list = []
    _stub_probe(monkeypatch, proc=_Proc(1, stderr="refused"), seen=seen)
    connections.probe(kubeconfig="/k", context="c")
    connections.probe(kubeconfig="/k", context="c")

    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert all(path.name.startswith("probe-") for path in seen)
    # Never the old fixed name, and nothing left behind.
    assert all(path.name != "probe.kubeconfig" for path in seen)
    assert not any(path.exists() for path in seen)


# ------------------------------------------------------------ pair/activate


def test_pair_without_any_kubeconfig_says_so(state_dir, monkeypatch) -> None:
    monkeypatch.setattr(connections, "discover_candidates", list)
    result = connections.pair_and_activate("https://host.docker.internal:11259")
    assert result["activated"] is None
    assert result["reason"] == "NO_KUBECONFIG"
    assert result["attempts"] == []
    assert "no kubeconfig" in result["advice"].lower()


def _candidate(kubeconfig: str = "/host-kube/config") -> connections.Candidate:
    return connections.Candidate(
        id="abc",
        source="mounted",
        label="vcluster-docker_dev  (mounted)",
        kubeconfig=kubeconfig,
        context="vcluster-docker_dev",
        cluster="vcluster-docker_dev",
        server="https://localhost:10093",
        environment="VCLUSTER",
    )


def test_pair_explains_a_foreign_api_server(state_dir, monkeypatch) -> None:
    monkeypatch.setattr(connections, "discover_candidates", lambda: [_candidate()])
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(
            False,
            connections.REASON_UNAUTHORIZED,
            detail="error: You must be logged in to the server",
            reason=connections.REASON_UNAUTHORIZED,
        ),
    )
    result = connections.pair_and_activate("https://host.docker.internal:10093")
    assert result["activated"] is None
    assert result["reason"] == connections.REASON_UNAUTHORIZED
    assert "not the cluster these credentials belong to" in result["advice"]
    assert result["attempts"][0]["reason"] == connections.REASON_UNAUTHORIZED


def test_pair_activates_the_kubeconfig_that_opens_the_endpoint(
    state_dir, monkeypatch, tmp_path
) -> None:
    # A real file, because activate() copies it; the kubectl rewrite is stubbed.
    source = tmp_path / "host-kubeconfig"
    source.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    monkeypatch.setattr(
        connections, "discover_candidates", lambda: [_candidate(str(source))]
    )
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(True, "OK", server_version="v1.30.4"),
    )

    def fake_materialise(target, **_kwargs):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
        return target

    monkeypatch.setattr(connections, "materialise_to", fake_materialise)

    result = connections.pair_and_activate("https://host.docker.internal:11259")
    assert result["reason"] == "ACTIVATED"
    assert result["activated"]["server_override"] == "https://host.docker.internal:11259"
    assert result["activated"]["insecure_skip_tls_verify"] is True
    # The kubeconfig's own server is kept so the UI can explain the override.
    assert result["activated"]["server"] == "https://localhost:10093"
    assert result["activated"]["effective_kubeconfig"] == str(
        state_dir / "connections" / "effective.kubeconfig"
    )
    assert connections.load_active() is not None


def test_endpoint_key_collapses_loopback_spellings() -> None:
    """`localhost:11259` and `127.0.0.1:11259` are the same API server.

    A kubeconfig commonly names one spelling where discovery found the other.
    Treating them as different stopped the app preferring the credentials that
    already name the right port, which is how a native WSL run ended up
    preferring the default gateway over loopback.
    """
    assert connections._endpoint_key("https://localhost:11259") == ("127.0.0.1", "11259")
    assert connections._endpoint_key("https://127.0.0.1:11259") == ("127.0.0.1", "11259")
    assert connections._endpoint_key("http://localhost:8080") == ("127.0.0.1", "8080")
    # A real host is left alone.
    assert connections._endpoint_key("https://host.docker.internal:11259") == (
        "host.docker.internal",
        "11259",
    )


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        ("https://host.docker.internal:11259", ("host.docker.internal", "11259")),
        ("https://localhost:10093", ("127.0.0.1", "10093")),
        ("https://10.0.0.1", ("10.0.0.1", "443")),
        ("host.docker.internal:6443", ("host.docker.internal", "6443")),
    ],
)
def test_endpoint_key_normalises_server_urls(server: str, expected: tuple) -> None:
    assert connections._endpoint_key(server) == expected


# -------------------------------------------------------- wire-format helpers


def test_camel_row_matches_the_browser_types() -> None:
    row = api._camel_row(
        connections.ActiveConnection(
            candidate_id="a",
            kubeconfig="/k",
            context="c",
            namespace="n",
            server_override="https://host.docker.internal:11259",
            insecure_skip_tls_verify=True,
            environment="VCLUSTER",
            label="l",
            server="https://localhost:10093",
            effective_kubeconfig="/e",
        ).as_dict()
    )
    assert row["candidateId"] == "a"
    assert row["serverOverride"] == "https://host.docker.internal:11259"
    assert row["insecureSkipTlsVerify"] is True
    assert row["effectiveKubeconfig"] == "/e"
    assert row["server"] == "https://localhost:10093"
    assert row["updatedAt"] > 0
    assert not [key for key in row if "_" in key]


def test_camel_row_recurses_into_nested_dumps() -> None:
    row = api._camel_row(
        {"server_version": "v1.30.4", "probe": {"namespace_count": 2, "latency_ms": 12}}
    )
    assert row == {
        "serverVersion": "v1.30.4",
        "probe": {"namespaceCount": 2, "latencyMs": 12},
    }


def test_host_only_warning_fires_for_a_loopback_server_without_an_override() -> None:
    warnings = api._unreachable_warning(
        connections.ActiveConnection(server="https://localhost:10093")
    )
    assert warnings and "container itself" in warnings[0]


def test_host_only_warning_is_silent_once_an_override_is_set() -> None:
    conn = connections.ActiveConnection(
        server="https://localhost:10093",
        server_override="https://host.docker.internal:11259",
    )
    assert api._unreachable_warning(conn) == []


def test_host_only_warning_ignores_a_routable_server() -> None:
    assert (
        api._unreachable_warning(connections.ActiveConnection(server="https://10.0.0.1:6443"))
        == []
    )



# ------------------------------------------------------- automatic connection
#
# The console is expected to find the cluster by itself. The Docker/WSL case is
# the hard one: a vcluster kubeconfig names `https://localhost:10093`, which
# inside a container is the container itself, so the only way in is to pair the
# kubeconfig with a discovered host endpoint.


def _discovered(
    server: str, *, source: str = "docker", container: str = "vcluster.cp.dev"
) -> dict:
    return {
        "server": server,
        "source": source,
        "container": container,
        "kind": "VCLUSTER",
        "version": "v1.30.4",
    }


def _stub_activate(monkeypatch) -> None:
    def fake_materialise(target, **_kwargs):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
        return target

    monkeypatch.setattr(connections, "materialise_to", fake_materialise)


def test_auto_connect_pairs_a_discovered_endpoint(state_dir, monkeypatch, tmp_path) -> None:
    """The kubeconfig's own server is unreachable; a detected endpoint is not."""
    source = tmp_path / "host-kubeconfig"
    source.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    monkeypatch.setattr(connections, "discover_candidates", lambda: [_candidate(str(source))])
    monkeypatch.setattr(
        connections,
        "reachable_endpoints",
        lambda: [_discovered("https://host.docker.internal:11259")],
    )
    _stub_activate(monkeypatch)

    seen: list[str] = []

    def fake_probe(**kwargs):
        seen.append(kwargs.get("server_override", ""))
        # Only the discovered endpoint opens the cluster.
        reachable = kwargs.get("server_override") == "https://host.docker.internal:11259"
        return connections.ProbeResult(
            reachable,
            "OK" if reachable else connections.REASON_UNREACHABLE,
            server_version="v1.30.4" if reachable else "",
            reason="" if reachable else connections.REASON_UNREACHABLE,
        )

    monkeypatch.setattr(connections, "probe", fake_probe)

    report = connections.auto_connect()
    assert report["reason"] == "ACTIVATED"
    assert report["activated"]["server_override"] == "https://host.docker.internal:11259"
    assert report["activated"]["insecure_skip_tls_verify"] is True
    assert report["detected"]["container"] == "vcluster.cp.dev"
    assert report["serverVersion"] == "v1.30.4"
    # The override was tried before the kubeconfig's own server.
    assert seen[0] == "https://host.docker.internal:11259"
    assert connections.load_active() is not None


def test_auto_connect_falls_back_to_the_kubeconfigs_own_server(
    state_dir, monkeypatch, tmp_path
) -> None:
    """Docker Desktop and remote clusters need no override at all."""
    source = tmp_path / "host-kubeconfig"
    source.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    monkeypatch.setattr(connections, "discover_candidates", lambda: [_candidate(str(source))])
    monkeypatch.setattr(connections, "reachable_endpoints", list)
    _stub_activate(monkeypatch)
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(True, "OK", server_version="v1.29.0"),
    )

    report = connections.auto_connect()
    assert report["reason"] == "ACTIVATED"
    assert report["activated"]["server_override"] == ""
    assert report["activated"]["insecure_skip_tls_verify"] is False
    assert report["detected"] is None


def test_auto_connect_without_a_kubeconfig_says_how_to_fix_it(state_dir, monkeypatch) -> None:
    monkeypatch.setattr(connections, "discover_candidates", list)
    monkeypatch.setattr(connections, "reachable_endpoints", list)
    report = connections.auto_connect()
    assert report["activated"] is None
    assert report["reason"] == "NO_KUBECONFIG"
    assert "mount" in report["advice"].lower()


def test_auto_connect_reports_why_every_pairing_failed(state_dir, monkeypatch, tmp_path) -> None:
    """A foreign API server that answers anonymously must be named as such."""
    source = tmp_path / "host-kubeconfig"
    source.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    monkeypatch.setattr(connections, "discover_candidates", lambda: [_candidate(str(source))])
    monkeypatch.setattr(
        connections,
        "reachable_endpoints",
        lambda: [_discovered("https://host.docker.internal:10093", source="sweep", container="")],
    )
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(
            False,
            connections.REASON_UNAUTHORIZED,
            detail="error: You must be logged in to the server (401)",
            reason=connections.REASON_UNAUTHORIZED,
        ),
    )
    report = connections.auto_connect()
    assert report["activated"] is None
    assert report["reason"] == connections.REASON_UNAUTHORIZED
    assert report["attempts"][0]["server"] == "https://host.docker.internal:10093"
    assert report["attempts"][0]["endpointSource"] == "sweep"




def test_check_active_reports_configured_but_unreachable(state_dir, monkeypatch, tmp_path) -> None:
    """A pinned override goes stale when the cluster restarts.

    Settings used to say "connected" while every page rendered empty, because
    nothing ever asked whether the saved endpoint still answered.
    """
    source = tmp_path / "host-kubeconfig"
    source.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    monkeypatch.setattr(connections, "discover_candidates", lambda: [_candidate(str(source))])
    monkeypatch.setattr(connections, "reachable_endpoints", list)
    _stub_activate(monkeypatch)
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(True, "OK", server_version="v1.30.4"),
    )
    connections.activate("abc", server_override="https://host.docker.internal:11259")

    healthy = connections.check_active()
    assert healthy["configured"] is True
    assert healthy["reachable"] is True

    # The cluster restarts and the published port moves.
    monkeypatch.setattr(
        connections,
        "probe",
        lambda **_k: connections.ProbeResult(
            False,
            connections.REASON_UNREACHABLE,
            detail="connection refused",
            reason=connections.REASON_UNREACHABLE,
        ),
    )
    stale = connections.check_active()
    assert stale["configured"] is True
    assert stale["reachable"] is False
    assert stale["reason"] == connections.REASON_UNREACHABLE
    assert stale["server"] == "https://host.docker.internal:11259"


def test_check_active_reports_nothing_configured(state_dir) -> None:
    health = connections.check_active()
    assert health["configured"] is False
    assert health["reachable"] is False
    assert "no connection is active" in health["detail"]


def test_startup_autoconnect_is_skipped_when_a_connection_is_healthy(
    state_dir, monkeypatch, caplog
) -> None:
    """Startup must never replace a working connection."""
    import asyncio

    from app import main as app_main

    monkeypatch.setattr(
        connections,
        "check_active",
        lambda **_k: {"configured": True, "reachable": True, "context": "ctx", "server": "s"},
    )

    def fail(**_k):  # pragma: no cover - must not be reached
        raise AssertionError("auto_connect must not run when the connection is healthy")

    monkeypatch.setattr(connections, "auto_connect", fail)

    with caplog.at_level("INFO"):
        asyncio.run(app_main._autoconnect())
    assert "already healthy" in caplog.text


def test_startup_autoconnect_reconnects_a_stale_connection(state_dir, monkeypatch, caplog) -> None:
    import asyncio

    from app import main as app_main

    monkeypatch.setattr(
        connections,
        "check_active",
        lambda **_k: {
            "configured": True,
            "reachable": False,
            "reason": "UNREACHABLE",
            "server": "s",
        },
    )
    monkeypatch.setattr(
        connections,
        "auto_connect",
        lambda **_k: {
            "activated": {"context": "vcluster-docker_dev", "server": "https://localhost:10093"},
            "serverOverride": "https://host.docker.internal:11259",
            "detected": {"source": "docker"},
        },
    )

    with caplog.at_level("INFO"):
        asyncio.run(app_main._autoconnect())
    assert "auto-connected" in caplog.text
    assert "host.docker.internal:11259" in caplog.text
