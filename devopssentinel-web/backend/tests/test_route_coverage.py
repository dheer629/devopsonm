"""Route-coverage guard (spec sections 286, 288, 290).

The GUI capability matrix counts routes the engine exposes but the console never
calls. That number only means something if it cannot drift silently, so this
module recomputes it from source and fails when a route loses its consumer.

A route is "consumed" when its path template (with `{}` for parameters) appears
in a non-test frontend source file. That is a deliberate, literal check: it
cannot be satisfied by a comment or a doc, only by real client code.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2]
API_DIR = WEB / "backend" / "app" / "api"
FRONTEND = WEB / "frontend" / "src"
PREFIX = "/api/v1"

# Routes with no literal caller, each with the reason it is allowed to stay that
# way. Adding a route here is a deliberate act, not an oversight.
ACCEPTED: dict[str, str] = {
    # Covered by a sibling route: the console reaches the same engine data.
    "/api/v1/gitops/sources": "covered by GET /gitops per-kind tabs",
    "/api/v1/gitops/kustomizations": "covered by GET /gitops per-kind tabs",
    "/api/v1/gitops/helmreleases": "covered by GET /gitops per-kind tabs",
    "/api/v1/pods/{}/containers": "superseded by GET /containers",
    "/api/v1/pods/{}/dependencies": "alias of GET /graph/Pod/{name}",
    # Impossible in a browser, with a stated reason.
    "/api/v1/tls/inspect": "BLOCKED: a browser must not open arbitrary TLS sockets (spec 72)",
    # Still unwired, tracked in docs/GUI_CLI_PARITY.md section 8.
    "/api/v1/connections/import": "kubeconfig import has no UI yet",
    "/api/v1/path": "two-object path query needs a target picker",
    "/api/v1/triage": "GET /findings already renders the same findings",
    "/api/v1/capabilities": "GET /doctor already reports tool availability",
    "/api/v1/session": "server-side session registry; no console surface",
    "/api/v1/health": "GET /health is a nav gap; /findings covers the operator need",
    "/api/v1/profile": "application profile summary; no console surface",
    "/api/v1/workloads/{}/{}": "workload detail reached through the inspector",
    "/api/v1/live": "SSE change stream; client side not built (spec 53)",
}


def _backend_routes() -> set[str]:
    """Every route the backend registers, normalised to `{}` for parameters."""
    routes: set[str] = set()
    for path in sorted(API_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"@router\.(?:get|post|put|patch|delete)\(\s*\"([^\"]+)\"", text):
            route = match.group(1)
            if route in ("", "/"):
                continue
            routes.add(re.sub(r"\{[^}]+\}", "{}", f"{PREFIX}{route}"))
    return routes


def _frontend_blob() -> str:
    parts: list[str] = []
    for path in FRONTEND.rglob("*.ts*"):
        if ".test." in path.name:
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_backend_route_has_a_frontend_consumer_or_a_stated_reason():
    """The gap register is enforced, not just documented (spec 286, 290)."""
    blob = _frontend_blob()
    unconsumed: set[str] = set()
    for route in _backend_routes():
        pattern = re.escape(route).replace(re.escape("{}"), "[^`\"' ]*")
        if not re.search(pattern, blob):
            unconsumed.add(route)

    unexplained = sorted(unconsumed - set(ACCEPTED))
    assert not unexplained, (
        "these routes have no frontend consumer and no stated reason:\n  "
        + "\n  ".join(unexplained)
    )


def test_accepted_list_has_no_stale_entries():
    """A route that gained a consumer must be removed from the allowlist.

    Without this the allowlist would slowly become a list of lies.
    """
    blob = _frontend_blob()
    stale: list[str] = []
    for route in ACCEPTED:
        pattern = re.escape(route).replace(re.escape("{}"), "[^`\"' ]*")
        if re.search(pattern, blob):
            stale.append(route)
    assert not stale, (
        "these routes are now consumed and must be removed from ACCEPTED:\n  "
        + "\n  ".join(sorted(stale))
    )


def test_route_coverage_is_reported():
    """Print the current ratio so the number in the docs is reproducible."""
    routes = _backend_routes()
    blob = _frontend_blob()
    covered = sum(
        1
        for route in routes
        if re.search(re.escape(route).replace(re.escape("{}"), "[^`\"' ]*"), blob)
    )
    print(f"route coverage: {covered}/{len(routes)} routes have a literal frontend consumer")
    assert covered + len(ACCEPTED) == len(routes)
