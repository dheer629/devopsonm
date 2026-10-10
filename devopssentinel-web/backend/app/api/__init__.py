"""API routers for DevOpsSentinel Web."""

from . import (
    connections,
    gitops,
    graph,
    inspect,
    network,
    operations,
    pki,
    storage,
    system,
    workloads,
)

__all__ = [
    "system",
    "workloads",
    "graph",
    "gitops",
    "pki",
    "network",
    "storage",
    "operations",
    "inspect",
    "connections",
]
