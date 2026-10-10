"""Minimal, explicitly allowlisted read-only kubectl discovery.

The engine does not expose "list contexts" / "list namespaces" as a report,
nor observed resource usage, pod logs or a resource describe, so the adapter
performs a few narrowly-scoped, read-only calls:

* ``config get-contexts`` / ``config current-context`` -- scope pickers
* ``get namespaces`` -- scope picker
* ``get nodes`` -- the node InternalIP a NodePort is reachable on, so the
  opt-in live-data views (SQL console, Kafka topics) can prefill a working host
* ``top pods`` / ``top nodes`` -- live CPU/memory usage for the usage charts
* ``logs POD …`` -- the log viewer (the engine captures logs only interactively)
* ``describe KIND NAME`` / ``get KIND NAME -o yaml|json`` -- the resource
  description viewer; ``secret``/``secrets`` is deliberately excluded so a
  Secret payload is never requested
* ``get pod NAME -o json`` -- container discovery for the log viewer
* ``get events -o json`` -- namespace events for one object

Every call is argv-array, no-shell, timeout-bounded, and listed in the parity
matrix as ``backend read-only helper``. No other kubectl verb is permitted:
``_validate`` pins every accepted form and
:func:`app.security.assert_read_only` rejects mutation verbs before the process
is spawned.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
from pathlib import Path

from ..config import settings
from ..security import assert_read_only, validate_context, validate_name
from . import connections

_ALLOWED = {
    ("config", "get-contexts"),
    ("config", "current-context"),
    ("get", "namespaces"),
    ("get", "ns"),
    ("get", "nodes"),
    ("top", "pods"),
    ("top", "nodes"),
}

# Global flags that take a value and may precede the verb.
_VALUE_FLAGS = {"--context", "--kubeconfig", "--namespace", "--cluster", "--user"}

# Resource kinds the read-only description viewer may describe or fetch.
# ``secret``/``secrets`` is deliberately absent: a Secret's ``data`` is base64
# and would survive keyword redaction, so it is never requested. See
# docs/SECURITY.md -- "Reading Secret payloads / private keys" stays BLOCKED.
_DESCRIBABLE_KINDS = {
    "pod", "pods", "deployment", "deployments", "statefulset", "statefulsets",
    "daemonset", "daemonsets", "replicaset", "replicasets", "job", "jobs",
    "cronjob", "cronjobs", "service", "services", "endpoints", "endpointslice",
    "endpointslices", "configmap", "configmaps", "ingress", "ingresses",
    "networkpolicy", "networkpolicies", "persistentvolumeclaim",
    "persistentvolumeclaims", "serviceaccount", "serviceaccounts",
    "horizontalpodautoscaler", "horizontalpodautoscalers",
    "certificate", "certificates", "certificaterequest", "certificaterequests",
    "issuer", "issuers", "clusterissuer", "clusterissuers",
    "helmrelease", "helmreleases", "kustomization", "kustomizations",
    "gitrepository", "gitrepositories", "ocirepository", "ocirepositories",
}

# `kubectl logs` option surface -- bounded and read-only.
_LOG_VALUE_FLAGS = {"-c", "--container", "--tail", "--since"}
_LOG_BARE_FLAGS = {"--previous", "--timestamps"}
_SINCE_RE = re.compile(r"^[1-9][0-9]{0,5}(s|m|h)$")
_CONTAINER_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class KubeError(RuntimeError):
    pass


def _validate_logs(rest: list[str]) -> None:
    """``logs POD [-c CONTAINER] [--tail=N] [--since=D] [--previous] [--timestamps]``.

    kubectl accepts both ``--tail=500`` and ``--tail 500``; both are allowed so
    the viewer may build whichever form it likes.
    """
    if not rest:
        raise KubeError("logs requires a pod name")
    validate_name(rest[0], field="pod")
    index = 1
    while index < len(rest):
        token = rest[index]
        flag, equals, inline = token.partition("=")
        if flag in _LOG_VALUE_FLAGS:
            if equals:
                value = inline
                index += 1
            else:
                if index + 1 >= len(rest):
                    raise KubeError(f"{flag} requires a value")
                value = rest[index + 1]
                index += 2
            if flag in ("-c", "--container"):
                if not _CONTAINER_RE.match(value):
                    raise KubeError(f"invalid container name: {value!r}")
            elif flag == "--tail":
                if not (value == "-1" or value.isdigit()):
                    raise KubeError(f"invalid tail: {value!r}")
            elif not _SINCE_RE.match(value):
                raise KubeError(f"invalid since duration: {value!r}")
            continue
        if flag in _LOG_BARE_FLAGS:
            # `--previous` or `--previous=true` describe the same read.
            index += 1
            continue
        raise KubeError(f"disallowed logs flag: {token!r}")


def _validate_describe(rest: list[str]) -> None:
    """``describe KIND NAME`` for a non-Secret kind."""
    if len(rest) != 2 or rest[0].lower() not in _DESCRIBABLE_KINDS:
        raise KubeError(f"disallowed describe target: {' '.join(rest)}")
    validate_name(rest[1], field="name")


def _validate_get(rest: list[str]) -> None:
    """``get KIND NAME [-o yaml|json]`` for a non-Secret kind."""
    if not rest or rest[0].lower() not in _DESCRIBABLE_KINDS:
        raise KubeError(f"disallowed get target: {' '.join(rest)}")
    if len(rest) < 2:
        raise KubeError("get requires a resource name")
    validate_name(rest[1], field="name")
    if len(rest) == 2:
        return
    if len(rest) == 4 and rest[2] == "-o" and rest[3] in ("yaml", "json"):
        return
    raise KubeError(f"disallowed get options: {' '.join(rest[2:])}")


def _validate(args: list[str]) -> None:
    """Allow only the documented read-only invocations.

    Global flags may precede the verb, so locate the verb first instead of
    assuming it is at position 0. Mutation verbs are rejected outright.
    """
    assert_read_only(list(args))
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in _VALUE_FLAGS else 1
    verb = args[index] if index < len(args) else ""
    rest = args[index + 1 :]

    if verb == "logs":
        _validate_logs(rest)
        return
    if verb == "describe":
        _validate_describe(rest)
        return
    if verb == "get":
        head = rest[0] if rest else ""
        if head in ("namespaces", "ns", "nodes"):
            return
        if head == "events":
            # `get events [-o json|wide]`, scoped by --namespace; parsed in Python.
            if rest[1:] in ([], ["-o", "json"], ["-o", "wide"]):
                return
            raise KubeError(f"disallowed get events options: {' '.join(rest[1:])}")
        _validate_get(rest)
        return
    if verb in ("config", "top") and (verb, rest[0] if rest else "") in _ALLOWED:
        return
    raise KubeError(f"disallowed kubectl invocation: {' '.join(args)}")


async def _run(args: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    _validate(args)
    kubectl = shutil.which("kubectl")
    if not kubectl:
        raise KubeError("kubectl is not available on PATH")
    # Pin the connection the operator activated. Without this a container that
    # has no ~/.kube/config silently reports every cluster as empty.
    argv = [kubectl, *args]
    if "--kubeconfig" not in args:
        active = connections.active_kubeconfig()
        if active:
            argv = [kubectl, "--kubeconfig", active, *args]
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise KubeError("kubectl discovery timed out") from exc
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def kubeconfig_path() -> str:
    # The connection the operator activated wins over any ambient KUBECONFIG.
    active = connections.active_kubeconfig()
    if active:
        return active
    explicit = os.environ.get("KUBECONFIG", "")
    if explicit:
        return explicit.split(os.pathsep)[0]
    default = Path(os.environ.get("HOME", str(Path.home()))) / ".kube" / "config"
    return str(default)


async def list_contexts() -> list[str]:
    rc, out, err = await _run(["config", "get-contexts", "-o", "name"])
    if rc != 0:
        raise KubeError(err.strip() or "unable to list contexts")
    return [line.strip() for line in out.splitlines() if line.strip()]


async def current_context() -> str:
    rc, out, err = await _run(["config", "current-context"])
    if rc != 0:
        raise KubeError(err.strip() or "no current context")
    return out.strip()


async def list_namespaces(context: str = "") -> list[str]:
    args = []
    if context:
        args += ["--context", validate_context(context)]
    args += ["get", "namespaces", "-o", "name"]
    rc, out, err = await _run(args)
    if rc != 0:
        raise KubeError(err.strip() or "unable to list namespaces")
    return [line.strip().split("/", 1)[-1] for line in out.splitlines() if line.strip()]


def capabilities() -> dict[str, bool]:
    return {
        "engine": settings.engine_available(),
        "bash": settings.bash_available(),
        "kubectl": shutil.which("kubectl") is not None,
        "jq": shutil.which("jq") is not None,
        "openssl": shutil.which("openssl") is not None,
        "flux": shutil.which("flux") is not None,
        "helm": shutil.which("helm") is not None,
        "psql": shutil.which("psql") is not None,
        "kafka": shutil.which("kafka-topics.sh") is not None
        or shutil.which("kafka-topics") is not None,
    }


# --------------------------------------------------------------------------
# Live resource usage (read-only `kubectl top`)
#
# The engine reports declared requests/limits, not observed usage, so the
# adapter performs one more narrowly-scoped read-only call. `top` is not a
# mutation verb and is pinned in _ALLOWED above.
# --------------------------------------------------------------------------

_MEMORY_SUFFIX = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


def parse_cpu(value: str) -> float:
    """``250m`` -> 0.25 cores, ``1500000n`` -> 0.0015 cores, ``2`` -> 2.0."""
    text = (value or "").strip()
    if not text or text == "<unknown>":
        return 0.0
    try:
        if text.endswith("n"):
            return float(text[:-1]) / 1_000_000_000
        if text.endswith("u"):
            return float(text[:-1]) / 1_000_000
        if text.endswith("m"):
            return float(text[:-1]) / 1000
        return float(text)
    except ValueError:
        return 0.0


def parse_memory(value: str) -> int:
    """``364Mi`` -> bytes, ``1500K`` -> bytes, ``12345`` -> bytes."""
    text = (value or "").strip()
    if not text or text == "<unknown>":
        return 0
    for suffix, factor in _MEMORY_SUFFIX.items():
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _percent(value: str) -> float | None:
    text = (value or "").strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def parse_top_pods(output: str) -> list[dict]:
    """Parse `kubectl top pods --no-headers` (NAME CPU(cores) MEMORY(bytes))."""
    rows: list[dict] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, cpu, memory = parts[0], parts[-2], parts[-1]
        cores = parse_cpu(cpu)
        rows.append(
            {
                "name": name,
                "cpuMillicores": int(round(cores * 1000)),
                "cpuCores": round(cores, 4),
                "memoryBytes": parse_memory(memory),
            }
        )
    return rows


def parse_top_nodes(output: str) -> list[dict]:
    """Parse `kubectl top nodes --no-headers` (NAME CPU CPU% MEMORY MEMORY%)."""
    rows: list[dict] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cores = parse_cpu(parts[1])
        rows.append(
            {
                "name": parts[0],
                "cpuMillicores": int(round(cores * 1000)),
                "cpuCores": round(cores, 4),
                "cpuPercent": _percent(parts[2]),
                "memoryBytes": parse_memory(parts[3]),
                "memoryPercent": _percent(parts[4]),
            }
        )
    return rows


async def top_pods(context: str = "", namespace: str = "") -> list[dict]:
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    if namespace:
        args += ["--namespace", validate_name(namespace, field="namespace")]
    args += ["top", "pods", "--no-headers"]
    rc, out, err = await _run(args, timeout=25.0)
    if rc != 0:
        raise KubeError(err.strip() or "kubectl top pods failed")
    return parse_top_pods(out)


async def top_nodes(context: str = "") -> list[dict]:
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    args += ["top", "nodes", "--no-headers"]
    rc, out, err = await _run(args, timeout=25.0)
    if rc != 0:
        raise KubeError(err.strip() or "kubectl top nodes failed")
    return parse_top_nodes(out)


# --------------------------------------------------------------------------
# Node address (read-only `kubectl get nodes`)
#
# A NodePort is reachable on a *node* address, never on 127.0.0.1 -- which is
# why the documented `127.0.0.1:30432` / `127.0.0.1:30092` platform endpoints do
# not answer inside a vcluster (only the API port is published to the host).
# The opt-in live-data views use this to prefill a host that actually works.
# --------------------------------------------------------------------------

_NODE_ADDRESS_JSONPATH = (
    '{.items[0].status.addresses[?(@.type=="InternalIP")].address}'
)


def parse_node_address(output: str) -> str:
    """Return the first InternalIP kubectl printed.

    The jsonpath above emits a single bare address (or nothing at all when no
    node advertises an InternalIP), so the parser only has to survive stray
    whitespace and a multi-node fallback.
    """
    for line in (output or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


async def node_address(context: str = "") -> str:
    """First node InternalIP, or ``""`` when the cluster reports none."""
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    args += ["get", "nodes", "-o", f"jsonpath={_NODE_ADDRESS_JSONPATH}"]
    rc, out, err = await _run(args)
    if rc != 0:
        raise KubeError(err.strip() or "unable to read a node address")
    return parse_node_address(out)


# --------------------------------------------------------------------------
# Log viewer (read-only `kubectl logs`)
#
# The engine captures pod logs only through its interactive `logs_capture`
# menu; there is no `--logs` report mode. The adapter therefore issues one
# read-only `kubectl logs` per view. The option surface is pinned in
# `_validate_logs` (pod, container, tail, since, previous, timestamps) and the
# output is redacted by the API layer like every other stream.
# --------------------------------------------------------------------------


def logs_argv(
    pod: str,
    *,
    context: str = "",
    namespace: str = "",
    container: str = "",
    tail: int = 500,
    since: str = "",
    previous: bool = False,
    timestamps: bool = True,
) -> list[str]:
    """Build the argv for one read-only `kubectl logs` call."""
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    if namespace:
        args += ["--namespace", validate_name(namespace, field="namespace")]
    args += ["logs", validate_name(pod, field="pod")]
    if container:
        args += ["-c", container]
    args += [f"--tail={int(tail)}"]
    if since:
        args += [f"--since={since}"]
    if previous:
        args += ["--previous=true"]
    if timestamps:
        args += ["--timestamps=true"]
    return args


async def pod_logs(
    pod: str,
    *,
    context: str = "",
    namespace: str = "",
    container: str = "",
    tail: int = 500,
    since: str = "",
    previous: bool = False,
    timestamps: bool = True,
    timeout: float = 25.0,
) -> str:
    """One read-only `kubectl logs`; returns the raw (unredacted) stdout."""
    args = logs_argv(
        pod,
        context=context,
        namespace=namespace,
        container=container,
        tail=tail,
        since=since,
        previous=previous,
        timestamps=timestamps,
    )
    rc, out, err = await _run(args, timeout=timeout)
    if rc != 0:
        raise KubeError(err.strip() or out.strip() or "kubectl logs failed")
    return out


async def pod_containers(
    pod: str, *, context: str = "", namespace: str = "", timeout: float = 15.0
) -> list[str]:
    """Container names of one pod (init + app + ephemeral), read-only."""
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    if namespace:
        args += ["--namespace", validate_name(namespace, field="namespace")]
    args += ["get", "pod", validate_name(pod, field="pod"), "-o", "json"]
    rc, out, err = await _run(args, timeout=timeout)
    if rc != 0:
        raise KubeError(err.strip() or "unable to read pod containers")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return []
    spec = payload.get("spec") or {}
    names: list[str] = []
    for key in ("initContainers", "containers", "ephemeralContainers"):
        for entry in spec.get(key) or []:
            name = entry.get("name")
            if name:
                names.append(str(name))
    return names

# --------------------------------------------------------------------------
# Resource description viewer (read-only `describe` / `get -o yaml|json`)
#
# `secret`/`secrets` is excluded from `_DESCRIBABLE_KINDS`, so a Secret payload
# can never be requested here even if a caller asks for it.
# --------------------------------------------------------------------------


def describe_argv(
    kind: str,
    name: str,
    *,
    context: str = "",
    namespace: str = "",
    fmt: str = "describe",
) -> list[str]:
    """Build the argv for one read-only describe/get call."""
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    if namespace:
        args += ["--namespace", validate_name(namespace, field="namespace")]
    if fmt == "describe":
        args += ["describe", kind, name]
    elif fmt in ("yaml", "json"):
        args += ["get", kind, name, "-o", fmt]
    else:  # pragma: no cover - guarded by the API layer
        raise KubeError(f"unsupported description format: {fmt!r}")
    return args


async def describe_resource(
    kind: str,
    name: str,
    *,
    context: str = "",
    namespace: str = "",
    fmt: str = "describe",
    timeout: float = 25.0,
) -> str:
    """One read-only describe / get; returns the raw (unredacted) stdout."""
    args = describe_argv(kind, name, context=context, namespace=namespace, fmt=fmt)
    rc, out, err = await _run(args, timeout=timeout)
    if rc != 0:
        raise KubeError(err.strip() or out.strip() or f"kubectl {fmt} failed")
    return out


def events_argv(*, context: str = "", namespace: str = "") -> list[str]:
    """Build the argv for one read-only event listing.

    With no namespace the listing is cluster-wide. Without
    ``--all-namespaces`` kubectl silently reads only the ``default``
    namespace, which is usually empty — and the page then reports nothing
    rather than showing the events that exist elsewhere in the cluster.
    """
    args: list[str] = []
    if context:
        args += ["--context", validate_context(context)]
    if namespace:
        args += ["--namespace", validate_name(namespace, field="namespace")]
    else:
        args += ["--all-namespaces"]
    args += ["get", "events", "-o", "json"]
    return args


def _parse_events(payload: dict, *, namespace: str = "", name: str = "") -> list[dict]:
    """Normalize a ``kubectl get events -o json`` payload into table rows."""
    rows: list[dict] = []
    # Cluster-wide listings need the namespace in the label, or rows from
    # different namespaces are indistinguishable in the table.
    cluster_wide = not namespace
    for item in payload.get("items") or []:
        involved = item.get("involvedObject") or {}
        involved_name = str(involved.get("name", ""))
        if name and involved_name != name:
            continue
        label = f"{involved.get('kind', '')}/{involved_name}".strip("/")
        event_namespace = str(involved.get("namespace", ""))
        if cluster_wide and event_namespace:
            label = f"{event_namespace}/{label}"
        rows.append(
            {
                "time": item.get("lastTimestamp") or item.get("eventTime") or "",
                "type": item.get("type", ""),
                "reason": item.get("reason", ""),
                "object": label,
                "count": item.get("count", 1),
                "message": item.get("message", ""),
            }
        )
    rows.sort(key=lambda row: str(row["time"]), reverse=True)
    return rows


async def events_with_raw(
    *,
    context: str = "",
    namespace: str = "",
    name: str = "",
    timeout: float = 20.0,
) -> tuple[list[dict], str]:
    """Namespace events plus the command's stdout.

    A kubectl-backed route has to be able to present the same ``raw`` evidence
    shape as an engine-backed one, so the unparsed output is returned alongside
    the rows instead of being discarded.
    """
    args = events_argv(context=context, namespace=namespace)
    rc, out, err = await _run(args, timeout=timeout)
    if rc != 0:
        raise KubeError(err.strip() or "unable to read events")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return [], out
    return _parse_events(payload, namespace=namespace, name=name), out


async def namespace_events(
    *,
    context: str = "",
    namespace: str = "",
    name: str = "",
    timeout: float = 20.0,
) -> list[dict]:
    """Namespace events, optionally filtered to one involved object name."""
    rows, _ = await events_with_raw(
        context=context, namespace=namespace, name=name, timeout=timeout
    )
    return rows


def command_string(argv: list[str]) -> str:
    """A copy-pasteable `kubectl …` string for the raw expert view."""
    return "kubectl " + " ".join(shlex.quote(token) for token in argv)
