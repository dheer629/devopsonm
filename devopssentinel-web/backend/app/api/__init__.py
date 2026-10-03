"""API routers for DevOpsSentinel Web."""

from . import gitops, graph, network, operations, pki, storage, system, workloads

__all__ = [
    "system",
    "workloads",
    "graph",
    "gitops",
    "pki",
    "network",
    "storage",
    "operations",
]
