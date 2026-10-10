"""Automatic discovery of Kubernetes API endpoints reachable from a container.

A container cannot read the WSL filesystem, nor the Docker host's process list,
so "detect the cluster" has to mean *find the API server's published port and
prove it answers*. Three independent sources are combined:

* the **Docker socket**, when mounted read-only: every container is inspected for
  a Kubernetes fingerprint (vcluster, kind, k3s, minikube, kube-apiserver,
  rancher) and its published host ports become candidate API endpoints;
* a **host port sweep** of well-known Kubernetes API ports on
  ``host.docker.internal`` and the default gateway;
* the **kubeconfig** itself, which supplies the credentials and the context name.

Nothing here is guessed. A port only becomes a suggestion once ``/version``
returns a Kubernetes version object, and a pairing is only offered when the
kubeconfig actually authenticates against that endpoint.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import httpx

DOCKER_SOCKET = "/var/run/docker.sock"

# Containers that are a Kubernetes control plane, or host one.
_K8S_IMAGE_HINTS = (
    ("vcluster", "VCLUSTER"),
    ("loft-sh", "VCLUSTER"),
    ("kindest", "KIND"),
    ("rancher/k3s", "K3S"),
    ("k3s", "K3S"),
    ("minikube", "MINIKUBE"),
    ("kube-apiserver", "KUBERNETES"),
    ("k8s.gcr.io/kube-apiserver", "KUBERNETES"),
    ("registry.k8s.io/kube-apiserver", "KUBERNETES"),
    ("microk8s", "MICROK8S"),
    ("k0s", "K0S"),
    ("talos", "TALOS"),
    ("openshift", "OPENSHIFT"),
)

# Ports a Kubernetes API server is commonly published on.
_COMMON_API_PORTS = (6443, 8443, 443, 16443, 11259, 10093, 8444, 7443, 6444, 8080)

# Hosts a container can use to reach the machine running Docker.
_HOST_ALIASES = ("host.docker.internal", "gateway.docker.internal")

# The same host, when the app runs on it directly.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

# Container markers. Module constants so tests can point them at a fixture.
DOCKERENV_FILE = "/.dockerenv"
CGROUP_FILE = "/proc/1/cgroup"


def in_container() -> bool:
    """Are we running inside a container?

    Decides which host most likely publishes the cluster's API port: loopback
    when the app runs natively (WSL, bare Linux, macOS) and the Docker host when
    it does not.
    """
    if os.path.exists(DOCKERENV_FILE):
        return True
    try:
        with open(CGROUP_FILE, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    return any(
        marker in text for marker in ("docker", "kubepods", "containerd", "podman", "libpod")
    )


def _docker_hosts() -> list[str]:
    """Host aliases plus the container's own default gateway."""
    hosts = list(_HOST_ALIASES)
    try:
        with open("/proc/net/route", encoding="utf-8") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) > 2 and fields[1] == "00000000":
                    raw = fields[2]
                    octets = [str(int(raw[i : i + 2], 16)) for i in (6, 4, 2, 0)]
                    gateway = ".".join(octets)
                    if gateway not in ("0.0.0.0", "") and gateway not in hosts:
                        hosts.append(gateway)
                    break
    except OSError:  # pragma: no cover - non-Linux host
        pass
    for extra in os.environ.get("DSWEB_HOST_ALIASES", "").split(","):
        if extra.strip() and extra.strip() not in hosts:
            hosts.append(extra.strip())
    return hosts


def _sweep_hosts() -> list[str]:
    """Every host worth probing for a published API port, best guess first.

    A native run must try loopback: the cluster's published port is on the same
    machine, and the Docker-host alias is often *not* usable — a WSL Ubuntu
    install resolves ``host.docker.internal`` to the Windows LAN address, which
    the Windows firewall blocks, so the sweep would otherwise only find the
    default gateway and route every API call out of WSL and back.

    Both lists are probed and only endpoints that answer ``/version`` survive, so
    guessing wrong costs one probe and nothing else.
    """
    if in_container():
        return _docker_hosts()
    return [*_LOOPBACK_HOSTS, *_docker_hosts()]


# --------------------------------------------------------------- docker socket


def docker_available() -> bool:
    return os.path.exists(DOCKER_SOCKET)


def _docker_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=DOCKER_SOCKET)
    return httpx.Client(transport=transport, base_url="http://docker", timeout=10.0)


def _docker_get(path: str, params: dict | None = None) -> tuple[object | None, str]:
    """Return ``(payload, error)``. A discovery probe never raises."""
    if not docker_available():
        return None, f"{DOCKER_SOCKET} is not mounted into this container"
    try:
        with _docker_client() as client:
            response = client.get(path, params=params or {})
            response.raise_for_status()
            return response.json(), ""
    except Exception as exc:  # noqa: BLE001 - report, never raise
        return None, f"{type(exc).__name__}: {exc}"[:300]


def docker_status() -> dict:
    """Whether the socket is usable, and why not when it is not.

    The usual cause is permissions: the socket is ``root:docker`` with mode
    ``660`` while the application runs as an unprivileged user, so the container
    needs ``--group-add`` with the socket's group id.
    """
    payload, error = _docker_get("/containers/json", {"all": "true"})
    return {
        "mounted": docker_available(),
        "usable": payload is not None,
        "error": error,
    }


def docker_containers() -> list[dict]:
    """Every container the Docker engine knows about, or ``[]`` when unavailable."""
    payload, _ = _docker_get("/containers/json", {"all": "true"})
    return payload if isinstance(payload, list) else []


def _fingerprint(container: dict) -> str | None:
    haystack = " ".join(
        [
            str(container.get("Image", "")),
            " ".join(container.get("Names") or []),
            " ".join(container.get("Labels", {}).values() if container.get("Labels") else []),
        ]
    ).lower()
    for needle, label in _K8S_IMAGE_HINTS:
        if needle in haystack:
            return label
    return None


def _published_ports(container: dict) -> list[int]:
    ports: list[int] = []
    for entry in container.get("Ports") or []:
        host_port = entry.get("PublicPort")
        if isinstance(host_port, int) and host_port > 0:
            ports.append(host_port)
    return sorted(set(ports))


# ------------------------------------------------------------------ probing


def probe_api(server: str, timeout: float = 2.5) -> dict | None:
    """Return version info when ``server`` really answers as a Kubernetes API.

    ``/version`` is unauthenticated, so this is a safe reachability proof and
    never needs credentials.
    """
    url = server.rstrip("/") + "/version"
    try:
        with httpx.Client(verify=False, timeout=timeout, follow_redirects=False) as client:
            response = client.get(url)
            if response.status_code != 200:
                return None
            payload = response.json()
    except Exception:  # noqa: BLE001 - a probe must never raise
        return None
    if not isinstance(payload, dict):
        return None
    version = str(payload.get("gitVersion", ""))
    if not version and "major" not in payload:
        return None
    return {
        "server": server.rstrip("/"),
        "version": version,
        "platform": str(payload.get("platform", "")),
    }


# --------------------------------------------------------------- candidates


def _from_docker() -> tuple[list[dict], list[dict]]:
    """(Kubernetes-ish containers, candidate endpoints) from the Docker socket."""
    containers: list[dict] = []
    endpoints: list[dict] = []
    # A published port is on loopback when the app runs on the same machine as
    # Docker, and on the Docker host when the app runs in a container.
    hosts = _docker_hosts()[:2] if in_container() else list(_LOOPBACK_HOSTS)
    for container in docker_containers():
        label = _fingerprint(container)
        ports = _published_ports(container)
        name = (container.get("Names") or ["?"])[0].lstrip("/")
        if label is not None:
            containers.append(
                {
                    "name": name,
                    "image": str(container.get("Image", "")),
                    "state": str(container.get("State", "")),
                    "status": str(container.get("Status", "")),
                    "kind": label,
                    "ports": ports,
                }
            )
        if label is None:
            continue
        for port in ports:
            for host in hosts:
                endpoints.append(
                    {
                        "server": f"https://{host}:{port}",
                        "source": "docker",
                        "container": name,
                        "kind": label,
                    }
                )
    return containers, endpoints


def _from_sweep() -> list[dict]:
    """Well-known API ports on every host the app can reach."""
    out: list[dict] = []
    for host in _sweep_hosts():
        for port in _COMMON_API_PORTS:
            out.append(
                {
                    "server": f"https://{host}:{port}",
                    "source": "sweep",
                    "container": "",
                    "kind": "",
                }
            )
    return out


def _endpoint_host(server: str) -> str:
    """The hostname of an API server URL, lowercased."""
    from urllib.parse import urlsplit

    return (urlsplit(server).hostname or "").lower()


def _endpoint_rank(row: dict) -> tuple[int, str]:
    """Order suggestions by how likely they are to be the right cluster.

    1. **Docker-derived** — it names the Kubernetes container publishing the
       port, so it is evidence rather than a guess.
    2. **Loopback on a native run** — no NAT and no host firewall in the path.
    3. **Everything else** — a sweep hit that may be any API server on the host.
    """
    if row["source"] == "docker":
        return (0, row["server"])
    if not in_container() and _endpoint_host(row["server"]) in _LOOPBACK_HOSTS:
        return (1, row["server"])
    return (2, row["server"])


def discover_endpoints(timeout: float = 2.0, max_probes: int = 48) -> dict:
    """Probe every candidate endpoint in parallel and keep the real API servers."""
    containers, docker_endpoints = _from_docker()
    ordered: list[dict] = []
    seen: set[str] = set()
    for item in [*docker_endpoints, *_from_sweep()]:
        if item["server"] in seen:
            continue
        seen.add(item["server"])
        ordered.append(item)
    ordered = ordered[:max_probes]

    found: list[dict] = []
    if ordered:
        with ThreadPoolExecutor(max_workers=12) as pool:
            for item, probed in pool.map(
                lambda candidate: (candidate, probe_api(candidate["server"], timeout)), ordered
            ):
                if probed is None:
                    continue
                found.append({**item, **probed})
    # Best guess first: a Docker-derived endpoint is evidence, a loopback hit on
    # a native run avoids the host firewall, everything else is a sweep guess.
    found.sort(key=_endpoint_rank)
    return {
        "dockerAvailable": docker_available(),
        "docker": docker_status(),
        "socket": DOCKER_SOCKET,
        "containers": containers,
        "endpoints": found,
        "probed": len(ordered),
    }
