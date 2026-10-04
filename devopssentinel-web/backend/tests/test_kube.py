"""Read-only kubectl discovery guard tests."""

from __future__ import annotations

import pytest

from app.services.kube import KubeError, _validate


def test_allows_the_three_read_only_discovery_calls():
    _validate(["config", "get-contexts", "-o", "name"])
    _validate(["config", "current-context"])
    _validate(["get", "namespaces"])
    _validate(["get", "ns"])


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
    ):
        with pytest.raises((KubeError, PermissionError)):
            _validate(bad)
