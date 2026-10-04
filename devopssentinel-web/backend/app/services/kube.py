"""Minimal, explicitly allowlisted read-only kubectl discovery.

The engine does not expose "list contexts" / "list namespaces" as a report,
nor observed resource usage, so the adapter performs a few narrowly-scoped,
read-only calls:

* ``config get-contexts`` / ``config current-context`` -- scope pickers
* ``get namespaces`` -- scope picker
* ``top pods`` / ``top nodes`` -- live CPU/memory usage for the usage charts

Every call is argv-array, no-shell, timeout-bounded, and listed in the parity
matrix as ``backend read-only helper``. No other kubectl verb is permitted:
``_ALLOWED`` pins the exact verb pairs and :func:`app.security.assert_read_only`
rejects mutation verbs before the process is spawned.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from ..config import settings
from ..security import assert_read_only, validate_context, validate_name

_ALLOWED = {
    ("config", "get-contexts"),
    ("config", "current-context"),
    ("get", "namespaces"),
    ("get", "ns"),
    ("top", "pods"),
    ("top", "nodes"),
}

# Global flags that take a value and may precede the verb.
_VALUE_FLAGS = {"--context", "--kubeconfig", "--namespace", "--cluster", "--user"}


class KubeError(RuntimeError):
    pass


def _validate(args: list[str]) -> None:
    """Allow only the three read-only discovery invocations.

    Global flags may precede the verb, so locate the verb pair instead of
    assuming it is at position 0. Mutation verbs are rejected outright.
    """
    assert_read_only(list(args))
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in _VALUE_FLAGS else 1
    if tuple(args[index : index + 2]) not in _ALLOWED:
        raise KubeError(f"disallowed kubectl invocation: {' '.join(args)}")


async def _run(args: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    _validate(args)
    kubectl = shutil.which("kubectl")
    if not kubectl:
        raise KubeError("kubectl is not available on PATH")
    proc = await asyncio.create_subprocess_exec(
        kubectl, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise KubeError("kubectl discovery timed out") from exc
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def kubeconfig_path() -> str:
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
