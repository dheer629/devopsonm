"""Minimal, explicitly allowlisted read-only kubectl discovery.

The engine does not expose "list contexts" / "list namespaces" as a report,
so the adapter performs two narrowly-scoped, read-only discovery calls.
Both are argv-array, no-shell, timeout-bounded, and listed in the parity
matrix as ``backend read-only helper``. No other kubectl verb is permitted.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from ..config import settings
from ..security import assert_read_only, validate_context

_ALLOWED = {
    ("config", "get-contexts"),
    ("config", "current-context"),
    ("get", "namespaces"),
    ("get", "ns"),
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
