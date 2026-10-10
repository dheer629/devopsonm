"""Cluster connection manager.

The application previously assumed exactly one kubeconfig at ``$KUBECONFIG`` or
``~/.kube/config``. That is fine on a workstation and useless in a container,
which is why every cluster-facing page rendered empty.

This module makes the target cluster a first-class, configurable object:

* **discover** kubeconfig files from every plausible location (env, home, a
  mounted host directory, the WSL Windows drive, in-cluster service account),
* **classify** each context by environment (Docker Desktop, kind, minikube,
  k3d, vcluster, EKS/GKE/AKS, in-cluster, generic),
* **probe** a candidate so the operator sees reachability, server version and
  namespace count before trusting it,
* **materialise** an effective kubeconfig for the active connection, including
  an API-server override and an explicit TLS-skip opt-in, so a container can
  reach a cluster published on the Docker host, and
* **persist** the choice under the private state directory.

Everything here is read-only. Nothing is written outside the state directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import settings

# Where a mounted host kubeconfig is looked for inside a container.
HOST_KUBE_DIRS = ("/host-kube", "/kubeconfig")

# WSL exposes the Windows profile tree here.
WSL_USERS = Path("/mnt/c/Users")

_ENV_HINTS = (
    ("docker-desktop", "DOCKER_DESKTOP"),
    ("kind-", "KIND"),
    ("minikube", "MINIKUBE"),
    ("k3d-", "K3D"),
    ("k3s", "K3S"),
    ("microk8s", "MICROK8S"),
    ("vcluster", "VCLUSTER"),
    ("eks", "EKS"),
    ("gke_", "GKE"),
    ("aks", "AKS"),
    ("rancher", "RANCHER"),
    ("openshift", "OPENSHIFT"),
)

_SERVER_HINTS = (
    ("docker-desktop", "DOCKER_DESKTOP"),
    (".eks.amazonaws.com", "EKS"),
    ("googleapis.com", "GKE"),
    ("azmk8s.io", "AKS"),
    ("127.0.0.1", "LOCAL"),
    ("localhost", "LOCAL"),
    ("host.docker.internal", "LOCAL"),
)


class ConnectionError(RuntimeError):
    pass


@dataclass
class Candidate:
    """One selectable (kubeconfig, context) pair."""

    id: str
    source: str
    label: str
    kubeconfig: str
    context: str
    cluster: str = ""
    server: str = ""
    namespace: str = ""
    environment: str = "UNKNOWN"
    in_cluster: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbeResult:
    reachable: bool
    status: str
    server_version: str = ""
    namespace_count: int = 0
    latency_ms: int = 0
    detail: str = ""
    # Machine-readable cause of a failure, so callers can explain it honestly
    # instead of guessing. One of the REASON_* values, or "" when reachable.
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# Failure reasons. Deliberately coarse: each one maps to different operator
# advice, which is the whole point of classifying rather than dumping stderr.
REASON_UNAUTHORIZED = "UNAUTHORIZED"
REASON_FORBIDDEN = "FORBIDDEN"
REASON_UNREACHABLE = "UNREACHABLE"
REASON_TLS = "TLS"
REASON_TIMEOUT = "TIMEOUT"
REASON_INVALID = "INVALID"
REASON_FAILED = "FAILED"


def classify_failure(text: str) -> str:
    """Map a kubectl error line onto a stable reason.

    An API server that answers ``/version`` anonymously and then rejects the
    client certificate is the single most confusing case in a container: the
    endpoint looks healthy in a port scan but belongs to a different cluster.
    kubectl reports that as ``You must be logged in ...``, which this turns into
    :data:`REASON_UNAUTHORIZED` so the UI can say what actually happened.
    """
    low = (text or "").lower()
    if "must be logged in" in low or "unauthorized" in low or "credentials" in low:
        return REASON_UNAUTHORIZED
    if "forbidden" in low or " 403" in low or "(403" in low:
        return REASON_FORBIDDEN
    if (
        "refused" in low
        or "no route to host" in low
        or "network is unreachable" in low
        or "connection reset" in low
        or "i/o timeout" in low
        or "no such host" in low
    ):
        return REASON_UNREACHABLE
    if "x509" in low or "tls" in low or "certificate" in low:
        return REASON_TLS
    if "timeout" in low or "timed out" in low or "deadline" in low:
        return REASON_TIMEOUT
    if "no such context" in low or "not found" in low:
        return REASON_INVALID
    return REASON_FAILED


@dataclass
class ActiveConnection:
    """The connection the application currently uses."""

    candidate_id: str = ""
    kubeconfig: str = ""
    context: str = ""
    namespace: str = ""
    server_override: str = ""
    insecure_skip_tls_verify: bool = False
    environment: str = "UNKNOWN"
    label: str = ""
    # The API server named by the kubeconfig itself, before any override. A
    # vcluster kubeconfig says ``https://localhost:10093`` because that is the
    # host port-forward, which is unreachable from inside a container; keeping
    # it lets the UI explain why an empty override is not the same as "default".
    server: str = ""
    effective_kubeconfig: str = ""
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------- state


def _connections_dir() -> Path:
    path = Path(settings.state_dir) / "connections"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _active_file() -> Path:
    return _connections_dir() / "active.json"


def _imports_dir() -> Path:
    path = _connections_dir() / "imported"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------- discovery


def discover_kubeconfig_files() -> list[tuple[str, Path]]:
    """Every plausible kubeconfig file, as ``(source, path)``.

    Ordered by trust: an explicit environment variable first, then the local
    home directory, then a mounted host directory, then the WSL Windows tree.
    """
    found: list[tuple[str, Path]] = []

    for entry in os.environ.get("KUBECONFIG", "").split(os.pathsep):
        if entry.strip():
            found.append(("env", Path(entry.strip())))

    extra = os.environ.get("DSWEB_KUBECONFIG_DIR", "")
    if extra:
        for directory in extra.split(os.pathsep):
            base = Path(directory)
            if base.is_dir():
                for child in sorted(base.iterdir()):
                    if child.is_file():
                        found.append(("configured", child))

    home = Path(os.environ.get("HOME", str(Path.home())))
    kube_dir = home / ".kube"
    found.append(("home", kube_dir / "config"))
    if kube_dir.is_dir():
        for child in sorted(kube_dir.iterdir()):
            if child.is_file() and child.suffix in (".yaml", ".yml", ".kubeconfig", ".conf"):
                found.append(("home", child))

    for directory in HOST_KUBE_DIRS:
        base = Path(directory)
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_file():
                    found.append(("mounted", child))

    if WSL_USERS.is_dir():
        for user_dir in sorted(WSL_USERS.iterdir()):
            candidate = user_dir / ".kube" / "config"
            if candidate.is_file():
                found.append(("wsl", candidate))

    unique: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, path in found:
        try:
            if not path.is_file():
                continue
            key = str(path.resolve())
        except OSError:  # pragma: no cover - defensive
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append((source, path))
    return unique


def _kubectl() -> str:
    path = shutil.which("kubectl")
    if not path:
        raise ConnectionError("kubectl is not available on the server")
    return path


def _load_config(path: Path) -> dict:
    """``kubectl config view -o json`` for one file (never raises on bad YAML)."""
    import subprocess

    try:
        proc = subprocess.run(
            [_kubectl(), "--kubeconfig", str(path), "config", "view", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise ConnectionError(f"unable to read {path}: {exc}") from exc
    if proc.returncode != 0:
        raise ConnectionError(proc.stderr.strip() or f"unable to read {path}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ConnectionError(f"{path} is not a readable kubeconfig") from exc


def classify(context: str, cluster: str, server: str, in_cluster: bool) -> str:
    """Best-effort environment label from evidence, never from a guess."""
    if in_cluster:
        return "IN_CLUSTER"
    haystack = f"{context} {cluster}".lower()
    for needle, label in _ENV_HINTS:
        if needle in haystack:
            return label
    lowered = server.lower()
    for needle, label in _SERVER_HINTS:
        if needle in lowered:
            return label
    return "GENERIC" if server else "UNKNOWN"


def _candidate_id(source: str, path: str, context: str) -> str:
    digest = hashlib.sha256(f"{source}|{path}|{context}".encode()).hexdigest()
    return digest[:16]


def candidates_from_file(source: str, path: Path) -> list[Candidate]:
    """Every context inside one kubeconfig file."""
    try:
        config = _load_config(path)
    except ConnectionError:
        return []
    clusters = {
        entry.get("name", ""): (entry.get("cluster") or {})
        for entry in config.get("clusters") or []
    }
    rows: list[Candidate] = []
    for entry in config.get("contexts") or []:
        ctx = entry.get("name", "")
        if not ctx:
            continue
        body = entry.get("context") or {}
        cluster = str(body.get("cluster", ""))
        namespace = str(body.get("namespace", ""))
        server = str(clusters.get(cluster, {}).get("server", ""))
        rows.append(
            Candidate(
                id=_candidate_id(source, str(path), ctx),
                source=source,
                label=f"{ctx}  ({source})",
                kubeconfig=str(path),
                context=ctx,
                cluster=cluster,
                server=server,
                namespace=namespace,
                environment=classify(ctx, cluster, server, False),
            )
        )
    return rows


def discover_candidates() -> list[Candidate]:
    """All candidates from every discovered file, de-duplicated by id."""
    rows: list[Candidate] = []
    seen: set[str] = set()
    for source, path in discover_kubeconfig_files():
        for candidate in candidates_from_file(source, path):
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            rows.append(candidate)
    order = {"env": 0, "configured": 1, "home": 2, "mounted": 3, "wsl": 4, "imported": 5}
    rows.sort(key=lambda c: (order.get(c.source, 9), c.context))
    return rows


def find_candidate(candidate_id: str) -> Candidate | None:
    for candidate in discover_candidates():
        if candidate.id == candidate_id:
            return candidate
    return None


# ---------------------------------------------------------- materialisation


def _cluster_for(kubeconfig: Path, context: str) -> str:
    config = _load_config(kubeconfig)
    for entry in config.get("contexts") or []:
        if entry.get("name") == context:
            return str((entry.get("context") or {}).get("cluster", ""))
    return ""


def _kubectl_run(kubeconfig: Path, *args: str, timeout: float = 20.0):
    import subprocess

    return subprocess.run(
        [_kubectl(), "--kubeconfig", str(kubeconfig), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def materialise_to(
    target: Path,
    *,
    kubeconfig: str,
    context: str,
    server_override: str = "",
    insecure_skip_tls_verify: bool = False,
) -> Path:
    """Write a self-contained kubeconfig for one connection.

    ``kubectl`` performs the rewrite, so the transform is exactly the one
    kubectl itself would apply -- no hand-rolled YAML editing.
    """
    source = Path(kubeconfig)
    if not source.is_file():
        raise ConnectionError(f"kubeconfig not found: {kubeconfig}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass

    proc = _kubectl_run(target, "config", "use-context", context)
    if proc.returncode != 0:
        raise ConnectionError(proc.stderr.strip() or f"unknown context: {context}")

    if server_override or insecure_skip_tls_verify:
        cluster = _cluster_for(target, context)
        if not cluster:
            raise ConnectionError("the selected context does not name a cluster")
        args = ["config", "set-cluster", cluster]
        if server_override:
            args.append(f"--server={server_override}")
        if insecure_skip_tls_verify:
            args.append("--insecure-skip-tls-verify=true")
        proc = _kubectl_run(target, *args)
        if proc.returncode != 0:
            raise ConnectionError(proc.stderr.strip() or "unable to rewrite the cluster")
    return target


def _scratch_kubeconfig() -> Path:
    """A private scratch path for one probe.

    kubectl rewrites the file it is given (``config use-context``,
    ``config set-cluster``), so a single shared path is a data race: a second
    probe started while the first is still running can read a half-rewritten
    kubeconfig and report a false failure. One file per call removes that.
    """
    import uuid

    return _connections_dir() / f"probe-{os.getpid()}-{uuid.uuid4().hex[:12]}.kubeconfig"


def _discard_scratch(scratch: Path) -> None:
    """Delete a scratch kubeconfig and the lock file kubectl leaves beside it."""
    for leftover in (scratch, scratch.with_name(scratch.name + ".lock")):
        try:
            leftover.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - defensive
            pass


def probe(
    *,
    kubeconfig: str,
    context: str,
    server_override: str = "",
    insecure_skip_tls_verify: bool = False,
    timeout: float = 20.0,
) -> ProbeResult:
    """Reachability, server version and namespace count for one connection."""
    started = time.monotonic()
    scratch = _scratch_kubeconfig()
    try:
        try:
            materialise_to(
                scratch,
                kubeconfig=kubeconfig,
                context=context,
                server_override=server_override,
                insecure_skip_tls_verify=insecure_skip_tls_verify,
            )
        except ConnectionError as exc:
            return ProbeResult(
                False, REASON_INVALID, detail=str(exc), reason=REASON_INVALID
            )

        latency = int((time.monotonic() - started) * 1000)
        try:
            version = _kubectl_run(
                scratch, "version", "-o", "json", f"--request-timeout={int(timeout)}s",
                timeout=timeout + 5,
            )
        except Exception as exc:  # pragma: no cover - subprocess guards
            reason = classify_failure(str(exc))
            return ProbeResult(
                False, reason, latency_ms=latency, detail=str(exc), reason=reason
            )

        if version.returncode != 0:
            lines = (version.stderr or version.stdout).strip().splitlines()
            detail = (
                lines[0][:300]
                if lines
                else "kubectl could not reach the API server"
            )
            reason = classify_failure(detail)
            return ProbeResult(
                False, reason, latency_ms=latency, detail=detail, reason=reason
            )

        server_version = ""
        try:
            payload = json.loads(version.stdout)
            server_version = str((payload.get("serverVersion") or {}).get("gitVersion", ""))
        except json.JSONDecodeError:
            pass

        count = 0
        try:
            names = _kubectl_run(
                scratch, "get", "namespaces", "-o", "name",
                f"--request-timeout={int(timeout)}s", timeout=timeout + 5,
            )
            if names.returncode == 0:
                count = len([line for line in names.stdout.splitlines() if line.strip()])
        except Exception:  # pragma: no cover - subprocess guards
            count = 0

        return ProbeResult(
            True, "OK", server_version=server_version, namespace_count=count,
            latency_ms=int((time.monotonic() - started) * 1000),
            detail="reachable",
        )
    finally:
        _discard_scratch(scratch)


# ------------------------------------------------------- active connection


def load_active() -> ActiveConnection | None:
    path = _active_file()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return ActiveConnection(
        candidate_id=str(payload.get("candidate_id", "")),
        kubeconfig=str(payload.get("kubeconfig", "")),
        context=str(payload.get("context", "")),
        namespace=str(payload.get("namespace", "")),
        server_override=str(payload.get("server_override", "")),
        insecure_skip_tls_verify=bool(payload.get("insecure_skip_tls_verify", False)),
        environment=str(payload.get("environment", "UNKNOWN")),
        label=str(payload.get("label", "")),
        server=str(payload.get("server", "")),
        effective_kubeconfig=str(payload.get("effective_kubeconfig", "")),
        updated_at=float(payload.get("updated_at", 0) or 0),
    )


def save_active(conn: ActiveConnection) -> ActiveConnection:
    conn.updated_at = time.time()
    path = _active_file()
    path.write_text(json.dumps(conn.as_dict(), indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


def activate(
    candidate_id: str,
    *,
    namespace: str = "",
    server_override: str = "",
    insecure_skip_tls_verify: bool = False,
) -> ActiveConnection:
    """Make one discovered context the connection the whole app uses."""
    candidate = find_candidate(candidate_id)
    if candidate is None:
        raise ConnectionError(f"unknown connection: {candidate_id}")
    effective = materialise_to(
        _connections_dir() / "effective.kubeconfig",
        kubeconfig=candidate.kubeconfig,
        context=candidate.context,
        server_override=server_override,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
    )
    return save_active(
        ActiveConnection(
            candidate_id=candidate.id,
            kubeconfig=candidate.kubeconfig,
            context=candidate.context,
            namespace=namespace or candidate.namespace,
            server_override=server_override,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            environment=candidate.environment,
            label=candidate.label,
            server=candidate.server,
            effective_kubeconfig=str(effective),
        )
    )


def deactivate() -> None:
    for name in ("active.json", "effective.kubeconfig", "probe.kubeconfig"):
        try:
            (_connections_dir() / name).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - defensive
            pass


def import_kubeconfig(content: str, name: str = "imported") -> list[Candidate]:
    """Accept a pasted kubeconfig and return the contexts it contains."""
    if "apiVersion" not in content or "clusters" not in content:
        raise ConnectionError("the pasted content does not look like a kubeconfig")
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:40]
    target = _imports_dir() / f"{safe or 'imported'}.kubeconfig"
    target.write_text(content, encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    rows = candidates_from_file("imported", target)
    if not rows:
        raise ConnectionError("the pasted kubeconfig contains no usable context")
    return rows


# Bounded so a cold start with many kubeconfigs and many listening ports cannot
# stall the console. Each pairing attempt is also short: a reachable API server
# answers /version in milliseconds.
_AUTOCONNECT_TIMEOUT_S = 5.0
_AUTOCONNECT_MAX_CANDIDATES = 6
_AUTOCONNECT_MAX_ENDPOINTS = 6


def reachable_endpoints() -> list[dict]:
    """Host API endpoints that answered ``/version``, evidence first.

    Wrapped defensively: discovery talks to the Docker socket and the network,
    and a failure to discover is not a reason to fail to connect.
    """
    try:
        from . import discovery
    except ImportError:  # pragma: no cover - httpx is a hard dependency
        return []
    try:
        return list(discovery.discover_endpoints().get("endpoints") or [])
    except Exception:  # noqa: BLE001 - a probe must never raise
        return []


def _attempt_row(
    candidate: Candidate, result: ProbeResult, server: str, endpoint: dict | None
) -> dict:
    return {
        "candidateId": candidate.id,
        "context": candidate.context,
        "kubeconfig": candidate.kubeconfig,
        "environment": candidate.environment,
        "server": server or candidate.server,
        "serverOverride": server,
        "endpointSource": (endpoint or {}).get("source", ""),
        "endpointContainer": (endpoint or {}).get("container", ""),
        "reachable": result.reachable,
        "serverVersion": result.server_version,
        "reason": result.reason,
        "detail": result.detail,
    }


def _worst_reason(attempts: list[dict]) -> str:
    """The most actionable failure across every attempt."""
    reasons = [a.get("reason") or REASON_FAILED for a in attempts]
    for preferred in (
        REASON_UNAUTHORIZED,
        REASON_FORBIDDEN,
        REASON_TLS,
        REASON_UNREACHABLE,
        REASON_TIMEOUT,
        REASON_INVALID,
    ):
        if preferred in reasons:
            return preferred
    return REASON_FAILED


def auto_detect(*, timeout: float = 8.0, limit: int = 12) -> tuple[Candidate | None, list[dict]]:
    """Probe discovered candidates and return the first reachable one."""
    results: list[dict] = []
    best: Candidate | None = None
    for candidate in discover_candidates()[:limit]:
        result = probe(
            kubeconfig=candidate.kubeconfig, context=candidate.context, timeout=timeout
        )
        results.append({**candidate.as_dict(), "probe": result.as_dict()})
        if result.reachable and best is None:
            best = candidate
    return best, results


def auto_connect(
    *,
    timeout: float = _AUTOCONNECT_TIMEOUT_S,
    max_candidates: int = _AUTOCONNECT_MAX_CANDIDATES,
    max_endpoints: int = _AUTOCONNECT_MAX_ENDPOINTS,
) -> dict:
    """Find a reachable cluster and activate it, with no operator input.

    Two sources are tried, in order:

    1. **Discovered endpoints.** ``reachable_endpoints`` keeps only host ports
       that answered ``/version``. A vcluster kubeconfig names
       ``https://localhost:<forward-port>`` -- inside a container that is the
       container itself -- so the cluster is reachable *only* by overriding the
       server with a discovered endpoint and re-probing with the kubeconfig's
       own credentials. TLS verification is skipped for these attempts because
       the certificate is issued for ``localhost``, not for
       ``host.docker.internal``, and the endpoint is the Docker host itself.
    2. **Each kubeconfig's own server**, which is already correct for Docker
       Desktop, a remote cluster, or an in-cluster service account.

    Returns a report instead of raising, so a caller can explain a failure
    rather than leaving the console silently unconfigured.
    """
    candidates = discover_candidates()
    if not candidates:
        return {
            "activated": None,
            "attempts": [],
            "reason": "NO_KUBECONFIG",
            "advice": (
                "No kubeconfig was found on the server, so there are no "
                'credentials to pair with. Mount one with -v '
                '"$USERPROFILE/.kube:/host-kube:ro" and rescan.'
            ),
            "serverOverride": "",
            "detected": None,
            "serverVersion": "",
        }

    ordered = candidates[:max_candidates]
    attempts: list[dict] = []

    for endpoint in reachable_endpoints()[:max_endpoints]:
        server = endpoint["server"]
        # A candidate whose own server already names this host:port is the best
        # guess for which credentials open it, so try that pairing first.
        wanted = _endpoint_key(server)
        preferred = sorted(ordered, key=lambda c: _endpoint_key(c.server) != wanted)
        for candidate in preferred:
            result = probe(
                kubeconfig=candidate.kubeconfig,
                context=candidate.context,
                server_override=server,
                insecure_skip_tls_verify=True,
                timeout=timeout,
            )
            attempts.append(_attempt_row(candidate, result, server, endpoint))
            if result.reachable:
                try:
                    conn = activate(
                        candidate.id, server_override=server, insecure_skip_tls_verify=True
                    )
                except ConnectionError:  # pragma: no cover - defensive
                    continue
                return {
                    "activated": conn.as_dict(),
                    "attempts": attempts,
                    "reason": "ACTIVATED",
                    "advice": "",
                    "serverOverride": server,
                    "detected": endpoint,
                    "serverVersion": result.server_version,
                }

    for candidate in ordered:
        result = probe(
            kubeconfig=candidate.kubeconfig, context=candidate.context, timeout=timeout
        )
        attempts.append(_attempt_row(candidate, result, "", None))
        if result.reachable:
            try:
                conn = activate(candidate.id)
            except ConnectionError:  # pragma: no cover - defensive
                continue
            return {
                "activated": conn.as_dict(),
                "attempts": attempts,
                "reason": "ACTIVATED",
                "advice": "",
                "serverOverride": "",
                "detected": None,
                "serverVersion": result.server_version,
            }

    reason = _worst_reason(attempts)
    return {
        "activated": None,
        "attempts": attempts,
        "reason": reason,
        "advice": _pair_advice(reason, attempts[0]["server"] if attempts else "", attempts),
        "serverOverride": "",
        "detected": None,
        "serverVersion": "",
    }


def check_active(*, timeout: float = _AUTOCONNECT_TIMEOUT_S) -> dict:
    """Is the active connection still usable?

    A saved connection can be configured and still be dead. A vcluster's
    published port changes when the cluster restarts, so a pinned override goes
    stale: Settings reports "connected" while every page renders empty. Callers
    use this to decide whether to reconnect.
    """
    conn = load_active()
    if conn is None:
        return {
            "configured": False,
            "reachable": False,
            "reason": "",
            "detail": "no connection is active",
            "server": "",
            "serverVersion": "",
            "context": "",
            "environment": "UNKNOWN",
        }
    result = probe(
        kubeconfig=conn.kubeconfig,
        context=conn.context,
        server_override=conn.server_override,
        insecure_skip_tls_verify=conn.insecure_skip_tls_verify,
        timeout=timeout,
    )
    return {
        "configured": True,
        "reachable": result.reachable,
        "reason": result.reason,
        "detail": result.detail or result.status,
        "server": conn.server_override or conn.server,
        "serverVersion": result.server_version,
        "context": conn.context,
        "environment": conn.environment,
    }


def active_kubeconfig() -> str:
    """Path of the effective kubeconfig, or ``""`` when nothing is active."""
    conn = load_active()
    if conn and conn.effective_kubeconfig and Path(conn.effective_kubeconfig).is_file():
        return conn.effective_kubeconfig
    return ""


def active_environment() -> dict[str, str]:
    """Environment overrides so kubectl and the engine agree on the cluster."""
    path = active_kubeconfig()
    return {"KUBECONFIG": path} if path else {}


def _endpoint_key(server: str) -> tuple[str, str]:
    """``(host, port)`` of an API server URL, for a cheap identity check.

    Loopback spellings collapse to one host: a kubeconfig commonly names
    ``localhost:11259`` where discovery found ``127.0.0.1:11259``, and treating
    those as different would stop the app preferring the credentials that
    already name the right port.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(server if "://" in server else f"https://{server}")
    host = (parts.hostname or "").lower()
    if host in ("localhost", "::1", "[::1]"):
        host = "127.0.0.1"
    if parts.port:
        port = str(parts.port)
    else:
        port = "443" if parts.scheme == "https" else "80"
    return host, port


def _pair_advice(reason: str, server: str, attempts: list[dict]) -> str:
    """Operator-facing advice for a failed pairing, keyed on the real cause."""
    if reason == REASON_UNAUTHORIZED:
        return (
            f"{server} is a Kubernetes API server, but it is not the cluster "
            "these credentials belong to: it answered /version anonymously and "
            "then rejected the client certificate. Pick the endpoint that names "
            "a Kubernetes container (the scan labels it 'verified'), or paste "
            "that API server into the API server override and press Activate."
        )
    if reason == REASON_FORBIDDEN:
        return (
            f"{server} accepted the certificate but denied the request (403). "
            "The credentials are valid for a different cluster or lack "
            "cluster-scoped read access."
        )
    if reason == REASON_TLS:
        return (
            f"TLS negotiation with {server} failed. Tick 'Skip TLS verification "
            "for the API server' and try again."
        )
    if reason == REASON_UNREACHABLE:
        return (
            f"{server} refused the connection. It may have stopped since the "
            "scan — press Scan for clusters and try the endpoint that answers."
        )
    if reason == REASON_TIMEOUT:
        return f"{server} did not answer in time. Retry, or raise the timeout."
    if reason == REASON_INVALID:
        return "kubectl could not build a kubeconfig for that endpoint; see the detail above."
    detail = next(
        (a.get("detail") for a in attempts if a.get("detail")),
        "no detail was reported",
    )
    return f"No kubeconfig authenticated against {server}: {detail}"


def pair_and_activate(server: str, *, timeout: float = 12.0) -> dict:
    """Find the kubeconfig that opens ``server``, then activate it.

    This is the one-click container path: endpoint discovery proves the API
    server is reachable, this proves which credentials open it, and activation
    pins the result so every page follows it.

    A port sweep finds every API server on the host, including ones that are
    not ours — they answer ``/version`` anonymously and then reject the client
    certificate with a 401. That case is reported as
    :data:`REASON_UNAUTHORIZED` with advice, rather than being mistaken for a
    missing kubeconfig.
    """
    candidates = discover_candidates()
    if not candidates:
        return {
            "activated": None,
            "attempts": [],
            "reason": "NO_KUBECONFIG",
            "advice": (
                "No kubeconfig was found on the server, so there are no "
                'credentials to pair with. Mount one with -v '
                '"$USERPROFILE/.kube:/host-kube:ro" and press Rescan.'
            ),
        }

    # Try the kubeconfig whose own API server already points at this host:port
    # first. It is only a hint (a vcluster's kubeconfig often names a host
    # port-forward instead of the published port), so a miss falls through to
    # every other candidate.
    wanted = _endpoint_key(server)
    ordered = sorted(candidates, key=lambda c: _endpoint_key(c.server) != wanted)

    attempts: list[dict] = []
    for candidate in ordered:
        result = probe(
            kubeconfig=candidate.kubeconfig,
            context=candidate.context,
            server_override=server,
            insecure_skip_tls_verify=True,
            timeout=timeout,
        )
        attempts.append(
            {
                "context": candidate.context,
                "kubeconfig": candidate.kubeconfig,
                "environment": candidate.environment,
                "reachable": result.reachable,
                "serverVersion": result.server_version,
                "reason": result.reason,
                "detail": result.detail,
            }
        )
        if result.reachable:
            conn = activate(
                candidate.id, server_override=server, insecure_skip_tls_verify=True
            )
            return {
                "activated": conn.as_dict(),
                "attempts": attempts,
                "reason": "ACTIVATED",
                "advice": "",
            }

    reasons = [a.get("reason") or REASON_FAILED for a in attempts]
    for preferred in (
        REASON_UNAUTHORIZED,
        REASON_FORBIDDEN,
        REASON_TLS,
        REASON_UNREACHABLE,
        REASON_TIMEOUT,
        REASON_INVALID,
    ):
        if preferred in reasons:
            reason = preferred
            break
    else:
        reason = REASON_FAILED
    return {
        "activated": None,
        "attempts": attempts,
        "reason": reason,
        "advice": _pair_advice(reason, server, attempts),
    }
