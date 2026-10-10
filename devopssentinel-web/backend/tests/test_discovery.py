"""Discovery tests.

The host list discovery sweeps is the difference between finding a cluster and
reporting nothing, and the right answer depends on where the app is running:
loopback on a native host, the Docker host inside a container. These tests pin
both, because getting it wrong is silent — the sweep simply finds nothing.
"""

from __future__ import annotations

from app.services import discovery


# ------------------------------------------------------------ in_container


def test_in_container_is_false_without_any_marker(tmp_path, monkeypatch) -> None:
    """A plain WSL Ubuntu is a VM, not a container.

    ``/.dockerenv`` does not exist and ``/proc/1/cgroup`` is ``0::/init.scope``,
    which is what this pins.
    """
    cgroup = tmp_path / "cgroup"
    cgroup.write_text("0::/init.scope\n", encoding="utf-8")
    monkeypatch.setattr(discovery, "DOCKERENV_FILE", str(tmp_path / "nope"))
    monkeypatch.setattr(discovery, "CGROUP_FILE", str(cgroup))
    assert discovery.in_container() is False


def test_in_container_detects_dockerenv(tmp_path, monkeypatch) -> None:
    marker = tmp_path / ".dockerenv"
    marker.write_text("", encoding="utf-8")
    monkeypatch.setattr(discovery, "DOCKERENV_FILE", str(marker))
    assert discovery.in_container() is True


def test_in_container_detects_a_docker_cgroup(tmp_path, monkeypatch) -> None:
    cgroup = tmp_path / "cgroup"
    cgroup.write_text(
        "12:devices:/docker/9f2c\n11:cpu:/kubepods/besteffort/pod1\n", encoding="utf-8"
    )
    monkeypatch.setattr(discovery, "DOCKERENV_FILE", str(tmp_path / "nope"))
    monkeypatch.setattr(discovery, "CGROUP_FILE", str(cgroup))
    assert discovery.in_container() is True


def test_in_container_is_false_when_the_cgroup_file_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(discovery, "DOCKERENV_FILE", str(tmp_path / "nope"))
    monkeypatch.setattr(discovery, "CGROUP_FILE", str(tmp_path / "also-nope"))
    assert discovery.in_container() is False


# --------------------------------------------------------------- host lists


def test_sweep_hosts_puts_loopback_first_on_a_native_run(monkeypatch) -> None:
    """The regression this exists for.

    Running natively, the cluster's published port is on loopback. The Docker
    host alias resolves to the LAN address, which a WSL install's Windows
    firewall blocks, so without loopback the sweep only finds the default
    gateway and every API call leaves WSL and comes back.
    """
    monkeypatch.setattr(discovery, "in_container", lambda: False)
    monkeypatch.setattr(
        discovery, "_docker_hosts", lambda: ["host.docker.internal", "172.28.208.1"]
    )
    hosts = discovery._sweep_hosts()
    assert hosts[:2] == ["127.0.0.1", "localhost"]
    assert "host.docker.internal" in hosts


def test_sweep_hosts_omits_loopback_inside_a_container(monkeypatch) -> None:
    """Inside a container ``127.0.0.1`` is the container itself."""
    monkeypatch.setattr(discovery, "in_container", lambda: True)
    monkeypatch.setattr(
        discovery, "_docker_hosts", lambda: ["host.docker.internal", "172.17.0.1"]
    )
    assert discovery._sweep_hosts() == ["host.docker.internal", "172.17.0.1"]


def test_from_sweep_covers_loopback_and_the_api_ports(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "in_container", lambda: False)
    monkeypatch.setattr(discovery, "_docker_hosts", lambda: ["host.docker.internal"])
    servers = {row["server"] for row in discovery._from_sweep()}
    assert "https://127.0.0.1:11259" in servers
    assert "https://localhost:11259" in servers
    assert "https://host.docker.internal:6443" in servers



def test_from_docker_uses_loopback_for_a_published_port_on_a_native_run(monkeypatch) -> None:
    """A published container port is on loopback when Docker shares the host."""
    monkeypatch.setattr(discovery, "in_container", lambda: False)
    monkeypatch.setattr(
        discovery,
        "docker_containers",
        lambda: [
            {
                "Names": ["/vcluster.cp.dev"],
                "Image": "ghcr.io/loft-sh/vm-container",
                "State": "running",
                "Status": "Up 5 days",
                "Ports": [{"PublicPort": 11259, "PrivatePort": 8443, "Type": "tcp"}],
            }
        ],
    )
    _, endpoints = discovery._from_docker()
    servers = {row["server"] for row in endpoints}
    assert "https://127.0.0.1:11259" in servers
    assert "https://host.docker.internal:11259" not in servers


def test_from_docker_uses_the_docker_host_inside_a_container(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "in_container", lambda: True)
    monkeypatch.setattr(
        discovery, "_docker_hosts", lambda: ["host.docker.internal", "172.17.0.1"]
    )
    monkeypatch.setattr(
        discovery,
        "docker_containers",
        lambda: [
            {
                "Names": ["/vcluster.cp.dev"],
                "Image": "ghcr.io/loft-sh/vm-container",
                "State": "running",
                "Status": "Up 5 days",
                "Ports": [{"PublicPort": 11259, "PrivatePort": 8443, "Type": "tcp"}],
            }
        ],
    )
    _, endpoints = discovery._from_docker()
    servers = {row["server"] for row in endpoints}
    assert "https://host.docker.internal:11259" in servers
    assert "https://127.0.0.1:11259" not in servers


# ------------------------------------------------------------------ ranking


def test_endpoint_rank_prefers_evidence_then_loopback(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "in_container", lambda: False)
    docker = {"server": "https://host.docker.internal:11259", "source": "docker"}
    loopback = {"server": "https://127.0.0.1:11259", "source": "sweep"}
    gateway = {"server": "https://172.28.208.1:11259", "source": "sweep"}
    assert discovery._endpoint_rank(docker) < discovery._endpoint_rank(loopback)
    assert discovery._endpoint_rank(loopback) < discovery._endpoint_rank(gateway)


def test_endpoint_rank_does_not_favour_loopback_inside_a_container(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "in_container", lambda: True)
    loopback = {"server": "https://127.0.0.1:11259", "source": "sweep"}
    gateway = {"server": "https://172.17.0.1:11259", "source": "sweep"}
    # Same rank: the second element is only a tie-breaker for stable ordering.
    assert discovery._endpoint_rank(loopback)[0] == discovery._endpoint_rank(gateway)[0]


def test_endpoint_host_parses_the_hostname() -> None:
    assert discovery._endpoint_host("https://127.0.0.1:11259") == "127.0.0.1"
    assert (
        discovery._endpoint_host("https://Host.Docker.Internal:11259") == "host.docker.internal"
    )
