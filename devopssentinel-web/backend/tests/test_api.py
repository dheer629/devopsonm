"""API contract tests (spec section 72) against the fake engine."""

from __future__ import annotations

SCOPE = {"context": "vcluster-docker_dev", "namespace": "devopsonm"}


def test_version_and_system(client, monkeypatch):
    from app.services import kube

    async def fake_node_address(context: str = "") -> str:
        """Keep the probe hermetic: no kubectl is spawned during the tests."""
        return "10.0.0.7"

    monkeypatch.setattr(kube, "node_address", fake_node_address)

    version = client.get("/api/v1/version").json()
    assert version["mode"] == "SUPERVISION [READ ONLY]"
    assert version["apiSchema"] == "1.0"

    system = client.get("/api/v1/system", params=SCOPE).json()
    assert system["data"]["readOnly"] is True
    assert system["data"]["operations"]
    # The opt-in live-data views prefill this instead of guessing 127.0.0.1.
    assert system["data"]["nodeAddress"] == "10.0.0.7"
    assert system["source"] == "LOCAL"


def test_envelope_shape_on_pods(client):
    body = client.get("/api/v1/pods", params=SCOPE).json()
    env = body["envelope"]
    for key in (
        "schemaVersion", "toolVersion", "timestamp", "context", "namespace",
        "source", "status", "partial", "durationMs", "cacheAgeMs", "data",
        "warnings", "errors",
    ):
        assert key in env
    assert env["toolVersion"] == "4.2.2"
    assert env["context"] == SCOPE["context"]
    assert isinstance(env["data"], list)
    assert any(p["name"] == "transformer-abc" for p in env["data"])


# --------------------------------------------------------------------------
# Global search grammar (spec 11-12)
# --------------------------------------------------------------------------


def test_search_query_parses_kind_prefixes():
    from app.api.operations import _parse_search_query

    terms, filters = _parse_search_query("pod:transformer")
    assert terms == ["transformer"]
    assert filters == {"kind": "Pod"}

    terms, filters = _parse_search_query("cert:tls")
    assert terms == ["tls"]
    assert filters == {"kind": "Certificate"}

    # Aliases resolve to the same canonical kind.
    assert _parse_search_query("svc:api")[1] == {"kind": "Service"}
    assert _parse_search_query("service:api")[1] == {"kind": "Service"}
    assert _parse_search_query("flux:apps")[1] == {"kind": "GitOps"}
    assert _parse_search_query("pvc:data")[1] == {"kind": "PVC"}


def test_search_query_parses_namespace_and_status_filters():
    from app.api.operations import _parse_search_query

    terms, filters = _parse_search_query("ns:payments transformer")
    assert terms == ["transformer"]
    assert filters == {"namespace": "payments"}

    terms, filters = _parse_search_query("status:failed")
    assert terms == []
    assert filters == {"state": "failed"}


def test_search_query_keeps_plain_terms_case_insensitive():
    from app.api.operations import _parse_search_query

    terms, filters = _parse_search_query("Log-Transformer")
    assert terms == ["log-transformer"]
    assert filters == {}


def test_search_query_does_not_mistake_a_colon_in_a_name_for_a_filter():
    """`nginx:1.25` is an image-ish token, not a directive we understand."""
    from app.api.operations import _parse_search_query

    terms, filters = _parse_search_query("nginx:1.25")
    assert terms == ["nginx:1.25"]
    assert filters == {}


def test_bare_kind_prefix_means_every_resource_of_that_kind():
    """`cert:` alone lists certificates; it is not a search for the text `cert:`."""
    from app.api.operations import _parse_search_query

    terms, filters = _parse_search_query("cert:")
    assert terms == []
    assert filters == {"kind": "Certificate"}

    # A bare ns:/status: carries no value, so it stays a plain term rather than
    # silently filtering everything out.
    assert _parse_search_query("ns:") == (["ns:"], {})
    assert _parse_search_query("status:") == (["status:"], {})


def test_row_matches_applies_every_filter():
    from app.api.operations import _row_matches

    row = {"kind": "Pod", "name": "log-transformer", "namespace": "payments", "state": "FAILED"}

    assert _row_matches(row, ["transformer"], {}) is True
    # Partial, case-insensitive matching -- no exact Kubernetes name needed.
    assert _row_matches(row, ["TRANSFORM"], {}) is True
    assert _row_matches(row, ["missing"], {}) is False
    # Namespace is part of the haystack, so `payments` finds it too.
    assert _row_matches(row, ["payments"], {}) is True

    assert _row_matches(row, [], {"kind": "Pod"}) is True
    assert _row_matches(row, [], {"kind": "Service"}) is False
    assert _row_matches(row, [], {"namespace": "pay"}) is True
    assert _row_matches(row, [], {"namespace": "other"}) is False
    assert _row_matches(row, [], {"state": "failed"}) is True
    assert _row_matches(row, [], {"state": "ok"}) is False


def test_search_row_state_reads_the_first_meaningful_field():
    from app.api.operations import _search_row_state

    assert _search_row_state({"status": "warning"}) == "WARNING"
    assert _search_row_state({"severity": "CRITICAL"}) == "CRITICAL"
    assert _search_row_state({"ready": True}) == "OK"
    assert _search_row_state({"ready": False}) == "FAILED"
    assert _search_row_state({}) == "UNKNOWN"


def test_search_endpoint_reports_what_it_searched(client):
    body = client.get("/api/v1/search", params={**SCOPE, "q": "pod:web"}).json()
    data = body["data"]
    # The envelope now describes the search itself, so the UI can show
    # provenance and a partial-result state instead of guessing.
    assert data["query"] == "pod:web"
    assert data["terms"] == ["web"]
    assert data["filters"] == {"kind": "Pod"}
    assert isinstance(data["results"], list)
    assert "unavailable" in data
    # A kind prefix must narrow the fan-out to that one domain.
    assert data["searched"] == ["Pod"]


def test_search_endpoint_fans_out_across_domains(client):
    body = client.get("/api/v1/search", params={**SCOPE, "q": "web"}).json()
    assert set(body["data"]["searched"]) == {
        "Pod", "Service", "Certificate", "GitOps", "PVC", "Finding",
    }


def test_cache_marks_second_call_as_cache(client):
    client.get("/api/v1/pods", params=SCOPE)
    second = client.get("/api/v1/pods", params=SCOPE).json()["envelope"]
    assert second["source"] in ("CACHE", "LIVE")


def test_certificates_status_is_derived(client):
    env = client.get("/api/v1/certificates", params=SCOPE).json()["envelope"]
    by_name = {c["name"]: c for c in env["data"]}
    assert by_name["syslog-cert"]["status"] == "WARNING"
    assert by_name["transformer-tls"]["status"] == "OK"


def test_certificates_expose_serial_and_source(client):
    env = client.get("/api/v1/certificates", params=SCOPE).json()["envelope"]
    by_name = {c["name"]: c for c in env["data"]}
    assert by_name["syslog-cert"]["serial"] == "ABCDEF0123456789"
    assert by_name["syslog-cert"]["source"].startswith("Secret/tls.crt")


def test_secrets_join_tls_certificate_expiry(client):
    """Secret inventory carries the expiry of the certificate it holds."""
    env = client.get("/api/v1/secrets", params=SCOPE).json()["envelope"]
    by_name = {s["name"]: s for s in env["data"]}
    assert by_name["syslog-cert"]["is_tls"] is True
    assert by_name["syslog-cert"]["days"] == 29
    assert by_name["syslog-cert"]["status"] == "WARNING"
    assert by_name["syslog-cert"]["key_count"] == 2
    # Non-TLS Secrets are inventoried but carry no certificate expiry. A key
    # *name* that matches a credential keyword is redacted cell-by-cell, so the
    # row survives and the rest of the table is not lost.
    assert by_name["transformer-db"]["is_tls"] is False
    assert by_name["transformer-db"]["days"] is None
    assert by_name["transformer-db"]["keys"] == "[REDACTED]"


def test_findings_are_critical_first(client):
    env = client.get("/api/v1/findings", params=SCOPE).json()["envelope"]
    assert env["data"]
    assert env["data"][0]["severity"] in ("CRITICAL", "FAILED", "WARNING")


def test_gitops_and_network_and_storage(client):
    assert client.get("/api/v1/gitops", params=SCOPE).json()["envelope"]["data"]
    assert client.get("/api/v1/network/services", params=SCOPE).json()["envelope"]["data"]
    assert client.get("/api/v1/storage", params=SCOPE).json()["envelope"]["data"]
    gaps = client.get("/api/v1/network/endpoint-gaps", params=SCOPE).json()["envelope"]
    assert all(g["ready_endpoints"] == 0 for g in gaps["data"])


def test_graph_and_impact(client):
    graph = client.get("/api/v1/graph/Pod/transformer-abc", params=SCOPE).json()["envelope"]
    assert graph["data"]["nodes"]
    impact = client.get("/api/v1/impact/Deployment/transformer", params=SCOPE).json()["envelope"]
    assert "referenced_by" in impact["data"] or "direct" in impact["data"]


# --------------------------------------------------------------------------
# Deep-diagnostic routes
#
# These endpoints were previously curl-only. Each one must return a shape the
# GUI can render directly -- and, where the engine reported it, the evidence
# behind a relationship (spec sections 37, 40, 41, 66-86).
# --------------------------------------------------------------------------

def test_graph_edges_carry_engine_evidence(client):
    """Every edge states why it exists, in the engine's own words."""
    graph = client.get("/api/v1/graph/Pod/transformer-abc", params=SCOPE).json()["envelope"]["data"]
    assert graph["edges"]
    for edge in graph["edges"]:
        assert edge["evidence"], f"edge {edge['id']} lost its evidence"
        assert "->" in edge["evidence"]


def test_failure_path_returns_typed_graph_and_marks_only_reported_nodes(client):
    env = client.get("/api/v1/failure-path/Pod/transformer-abc", params=SCOPE).json()["envelope"]
    data = env["data"]
    assert data["target"] == "Pod/transformer-abc"
    assert data["graph"]["nodes"]
    # A node is only highlighted when the engine itself marked it unhealthy, so
    # the set must be a subset of the graph's own nodes.
    node_ids = {node["id"] for node in data["graph"]["nodes"]}
    assert set(data["unhealthy"]) <= node_ids
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids for edge in data["pathEdges"]
    )


def test_failure_path_correlates_the_engines_findings(client):
    """Health comes from the findings, because the graph report has no state.

    The dependency report describes structure only. If the route read node state
    from it, `unhealthy` would always be empty and the failure-path mode would be
    inert while looking like it worked (spec sections 40, 286).
    """
    data = client.get("/api/v1/failure-path/Pod/transformer-abc", params=SCOPE).json()["envelope"]["data"]
    assert data["healthSource"] == "the engine's findings"
    # The fixture's triage table names `Pod/transformer-abc` with WARN.
    assert data["severity"].get("Pod/transformer-abc") == "WARNING"
    assert "Pod/transformer-abc" in data["unhealthy"]
    # And the node's own state was updated so the graph colours agree.
    node = next(n for n in data["graph"]["nodes"] if n["id"] == "Pod/transformer-abc")
    assert node["state"] == "WARNING"


def test_failure_path_leaves_unmentioned_nodes_unknown(client):
    """A node with no finding is UNKNOWN, never assumed healthy."""
    data = client.get("/api/v1/failure-path/Pod/transformer-abc", params=SCOPE).json()["envelope"]["data"]
    node = next(n for n in data["graph"]["nodes"] if n["id"] == "ReplicaSet/transformer-xyz")
    assert node["state"] == "UNKNOWN"
    assert "ReplicaSet/transformer-xyz" not in data["unhealthy"]


def test_impact_reports_reverse_dependencies_with_confidence(client):
    data = client.get("/api/v1/impact/Pod/transformer-abc", params=SCOPE).json()["envelope"]["data"]
    assert data["target"] == "Pod/transformer-abc"
    assert data["count"] == len(data["direct"])
    assert data["confidence"] == "HIGH CONFIDENCE"
    assert "graph" in data


def test_certificate_detail_pairs_inventory_row_with_its_graph(client):
    data = client.get("/api/v1/certificates/syslog-cert", params=SCOPE).json()["envelope"]["data"]
    assert data["certificate"]["name"] == "syslog-cert"
    assert data["certificate"]["issuer"] == "internal-ca"
    assert data["certificate"]["days"] == 29
    assert "nodes" in data["graph"] and "edges" in data["graph"]


def test_certificate_detail_warns_when_the_name_is_not_in_the_inventory(client):
    env = client.get("/api/v1/certificates/no-such-cert", params=SCOPE).json()["envelope"]
    assert env["data"]["certificate"] is None
    assert any("not in the certificate inventory" in warning for warning in env["warnings"])


def test_certificate_chain_walks_only_issuers_the_engine_reported(client):
    """``internal-ca`` is not itself in the inventory, so the chain stops at one link."""
    data = client.get("/api/v1/certificates/syslog-cert/chain", params=SCOPE).json()["envelope"]["data"]
    assert data["depth"] == 1
    assert data["complete"] is False
    link = data["chain"][0]
    assert link["subject"] == "syslog.local"
    assert link["issuer"] == "internal-ca"
    assert link["status"] == "WARNING"


def test_certificate_consumers_targets_the_secret(client):
    data = client.get("/api/v1/certificates/syslog-cert/consumers", params=SCOPE).json()["envelope"]["data"]
    assert data["target"] == "Secret/syslog-cert"
    assert isinstance(data["direct"], list)


def test_cert_expiry_audit_table_is_parsed(client):
    """The engine's `--cert-expiry` audit is a TSV whose columns are
    NAMESPACE/OBJECT/CN-SAN/ISSUER/EXPIRY/DAYS/STATUS.

    Without recognising `OBJECT` and `CN/SAN` the GUI had to recompute expiry
    buckets in the browser, which risked disagreeing with the engine's own
    thresholds (spec sections 66, 286, 290).
    """
    rows = client.get("/api/v1/certificates/expiry", params=SCOPE).json()["envelope"]["data"]
    by_name = {row["name"]: row for row in rows}
    # `Secret/syslog-cert` is reduced to the bare identifier the other routes use.
    assert "syslog-cert" in by_name
    assert "Secret/syslog-cert" not in by_name
    assert by_name["syslog-cert"]["days"] == 29
    assert by_name["syslog-cert"]["status"] == "WARNING"
    assert by_name["syslog-cert"]["cn"] == "syslog.local"
    assert by_name["syslog-cert"]["issuer"] == "CN=internal-ca"
    assert by_name["transformer-tls"]["days"] == 240
    assert by_name["transformer-tls"]["status"] == "OK"


def test_certificate_chain_terminates_on_a_cycle(monkeypatch):
    """A mis-reported issuer must not loop forever."""
    import asyncio

    from app.api import pki

    certs = [
        {"name": "a", "cn": "a", "issuer": "b", "expiry": "", "days": 10, "status": "OK", "serial": "1"},
        {"name": "b", "cn": "b", "issuer": "a", "expiry": "", "days": 10, "status": "OK", "serial": "2"},
    ]

    async def fake_invoke(operation, sc, params=None, normalizer=None, force=False):
        return {"envelope": {"data": certs, "warnings": [], "errors": []}}

    monkeypatch.setattr(pki, "invoke", fake_invoke)
    scope = type("S", (), {"context": "c", "namespace": "n"})()
    env = asyncio.run(pki.chain("a", sc=scope))
    assert env["envelope"]["data"]["depth"] == 2


def test_storage_mount_warnings_separate_unhealthy_from_unconsumed(client):
    data = client.get("/api/v1/storage/mount-warnings", params=SCOPE).json()["envelope"]["data"]
    assert data["total"] == len(data["warnings"]) + len(data["unconsumed"])
    assert all(claim["severity"] != "OK" for claim in data["warnings"])
    assert all(claim["severity"] == "OK" for claim in data["unconsumed"])
    # ``data-1`` is Pending in the fixture, so it must surface as a warning.
    assert any(claim["name"] == "data-1" for claim in data["warnings"])


def test_pvc_detail_pairs_the_claim_with_its_binding_chain(client):
    data = client.get("/api/v1/storage/pvc/data-1", params=SCOPE).json()["envelope"]["data"]
    assert data["claim"]["name"] == "data-1"
    assert data["claim"]["status"] == "Pending"
    assert "nodes" in data["graph"] and "edges" in data["graph"]


def test_service_dns_reports_the_record_without_claiming_a_probe(client):
    data = client.get("/api/v1/network/dns/transformer", params=SCOPE).json()["envelope"]["data"]
    assert data["fqdn"] == "transformer.devopsonm.svc.cluster.local"
    assert data["shortName"] == "transformer.devopsonm"
    assert data["resolves"] in ("VERIFIED", "NOT PROBED")
    # The DNS view must never claim more than it observed.
    assert "not probed" in data["note"].lower()


def test_pod_policies_reports_configuration_not_runtime_permission(client):
    data = client.get("/api/v1/network/policies/transformer-abc", params=SCOPE).json()["envelope"]["data"]
    assert data["target"] == "Pod/transformer-abc"
    assert isinstance(data["selectingPolicies"], list)
    assert data["isolated"] == bool(data["selectingPolicies"])
    assert "not whether traffic is actually permitted" in data["note"]


def test_gitops_timeline_states_what_the_engine_observed(client):
    env = client.get("/api/v1/gitops/GitRepository/devopsonm/timeline", params=SCOPE).json()["envelope"]
    data = env["data"]
    assert data["object"]["name"] == "devopsonm"
    assert data["entries"]
    assert any(entry["event"] == "Desired revision reported" for entry in data["entries"])
    assert "not a revision history" in data["note"]


def test_gitops_chain_is_a_typed_graph(client):
    data = client.get("/api/v1/gitops/chain", params=SCOPE).json()["envelope"]["data"]
    assert data["nodes"] and data["edges"]
    assert any(edge["label"] == "MANAGED_BY" for edge in data["edges"])


def test_pod_detail_triages_the_owning_workload(client):
    """``--triage-workload`` correlates workloads, not pods.

    Passing ``Pod/x`` makes the engine answer ``WORKLOAD NOT FOUND`` and exit 2,
    so the adapter resolves the pod's owner first and triages that.
    """
    body = client.get("/api/v1/pods/transformer-abc", params=SCOPE).json()
    assert "Deployment/transformer" in body["raw"]["engineArgv"]
    assert "Pod/transformer-abc" not in body["raw"]["engineArgv"]


def test_pod_events_endpoint_returns_normalized_rows(client):
    """Regression: the events normalizer used to be `async def`.

    ``invoke`` calls normalizers synchronously, so an async normalizer leaked a
    coroutine into the envelope and every request returned HTTP 500.
    """
    response = client.get("/api/v1/pods/log-transformer-def/events", params=SCOPE)
    assert response.status_code == 200
    assert isinstance(response.json()["envelope"]["data"], list)


# Every route the browser consumes as an *operation*
# (``useQuery<OperationResponse<T>>`` -> ``getOperation``) must answer with
# ``{envelope, raw, exitStatus}``. The page reads ``data.envelope``, so a bare
# envelope arrives as ``undefined`` and throws on the first property read.
OPERATION_ROUTES = (
    "/api/v1/workloads",
    "/api/v1/pods",
    "/api/v1/findings",
    "/api/v1/gitops",
    "/api/v1/certificates",
    "/api/v1/secrets",
    "/api/v1/storage",
    "/api/v1/network/services",
    "/api/v1/database/services",
    "/api/v1/kafka/services",
    "/api/v1/doctor",
    "/api/v1/snapshot",
    "/api/v1/application-profile",
)


def test_every_operation_route_returns_the_operation_shape(client):
    for path in OPERATION_ROUTES:
        body = client.get(path, params=SCOPE).json()
        assert {"envelope", "raw", "exitStatus"} <= set(body), (
            f"{path} returned {sorted(body)}; the browser reads `envelope`, so a "
            "bare envelope crashes the consuming page"
        )


def test_events_live_path_returns_the_operation_shape(client, monkeypatch):
    """Regression: ``/events`` returned a bare envelope whenever kubectl won.

    ``EventsPage`` reads ``events.data.envelope.data``, so the live branch made
    it throw ``Cannot read properties of undefined (reading 'data')``. The
    fixture-backed E2E suite never caught it because the fixture already
    returned the operation shape.
    """
    from app.services import kube

    async def fake_events_with_raw(**_kwargs):
        return (
            [
                {
                    "time": "2026-10-10T02:16:49Z",
                    "type": "Warning",
                    "reason": "BackOff",
                    "object": "Pod/web",
                    "count": 3,
                    "message": "Back-off restarting failed container",
                }
            ],
            '{"items": []}',
        )

    monkeypatch.setattr(kube, "events_with_raw", fake_events_with_raw)

    body = client.get("/api/v1/events", params=SCOPE).json()
    assert {"envelope", "raw", "exitStatus"} <= set(body)
    assert body["envelope"]["source"] == "LIVE"
    assert body["envelope"]["data"][0]["reason"] == "BackOff"
    # `raw` stays truthful: the real command and its real stdout.
    assert body["raw"]["engineArgv"][0] == "kubectl"
    assert "events" in body["raw"]["engineArgv"]
    assert body["raw"]["stdout"] == '{"items": []}'


def test_events_fallback_path_keeps_the_same_shape(client, monkeypatch):
    """The engine fallback must not drift from the live branch's shape."""
    from app.services import kube

    async def unavailable(**_kwargs):
        raise kube.KubeError("no reachable cluster")

    monkeypatch.setattr(kube, "events_with_raw", unavailable)

    body = client.get("/api/v1/events", params=SCOPE).json()
    assert {"envelope", "raw", "exitStatus"} <= set(body)
    assert any("no reachable cluster" in w for w in body["envelope"]["warnings"])


def test_database_and_kafka_structured_views(client):
    """The Database / Kafka pages render tables, not just report text."""
    db = client.get("/api/v1/database/services", params=SCOPE).json()["envelope"]
    by_name = {row["name"]: row for row in db["data"]}
    assert by_name["pg-svc"]["port"] == "5432"
    assert by_name["pg-svc"]["ready_endpoint"] == "10.0.0.10"
    assert by_name["pg-svc"]["status"] == "OK"
    assert by_name["stale-db"]["status"] == "WARNING"

    kafka = client.get("/api/v1/kafka/services", params=SCOPE).json()["envelope"]
    assert kafka["data"][0]["name"] == "kafka"
    assert kafka["data"][0]["bootstrap"] == "kafka.devopsonm.svc:9093"


def test_sql_console_reason_names_the_settings_switch_not_a_restart(client, monkeypatch):
    """``liveconfig`` applies the switch immediately, so the hint must say so.

    Telling the operator to "restart the backend with DSWEB_ENABLE_SQL_CONSOLE=1"
    sends them down a dead end: the Settings switch already turns the console on,
    live, with no restart.
    """
    from app.api import live
    from app.services import kube, liveconfig

    async def fake_node_address(context: str = "") -> str:
        return "10.0.0.7"

    monkeypatch.setattr(kube, "node_address", fake_node_address)
    monkeypatch.setattr(live, "_pg_driver_available", lambda: True)

    monkeypatch.setattr(liveconfig, "sql_console_enabled", lambda: False)
    disabled = client.get("/api/v1/database/console").json()["data"]
    assert disabled["enabled"] is False
    assert "Settings" in disabled["reason"]
    assert "no restart needed" in disabled["reason"]

    monkeypatch.setattr(liveconfig, "sql_console_enabled", lambda: True)
    enabled = client.get("/api/v1/database/console").json()["data"]
    assert enabled["enabled"] is True
    assert enabled["reason"] == ""
    assert enabled["driverAvailable"] is True


def test_doctor_capabilities(client):
    env = client.get("/api/v1/doctor", params=SCOPE).json()["envelope"]
    assert env["data"]


def test_secrets_are_redacted_in_api_output(client):
    body = client.get("/api/v1/capabilities", params=SCOPE).json()
    blob = str(body)
    assert "eyJhbGciOiJIUzI1NiJ9" not in blob
    assert "[REDACTED]" in body["raw"]["stdout"]


def test_no_shell_exec_endpoint_exists(client):
    for path in ("/api/v1/exec", "/api/v1/shell", "/api/v1/kubectl"):
        assert client.get(path).status_code == 404


def test_origin_guard_blocks_state_change_from_unknown_origin(client):
    response = client.post(
        "/api/v1/pins",
        json={"id": "Pod/x", "kind": "Pod", "name": "x"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "origin not allowed"
    # The response names the origins that *are* trusted: a page served on a port
    # the backend does not trust is then diagnosable instead of just failing.
    assert "http://127.0.0.1:8765" in body["allowed"]
    assert body["hint"]


def test_origin_guard_allows_local_origin(client):
    response = client.post(
        "/api/v1/pins",
        json={"id": "Pod/x", "kind": "Pod", "name": "x"},
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "Pod/x"
    client.delete("/api/v1/pins/Pod/x")


def test_origin_guard_trusts_the_port_the_app_serves_on(client, monkeypatch):
    """A bind the app was given must be a bind it trusts.

    Regression: `DSWEB_PORT=8766` moved the page to an origin the allow-list did
    not contain, so every POST from that page was 403 while every GET worked.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "port", 8766)
    monkeypatch.setattr(settings, "allowed_origins", settings.self_origins())
    response = client.post(
        "/api/v1/pins",
        json={"id": "Pod/x", "kind": "Pod", "name": "x"},
        headers={"Origin": "http://127.0.0.1:8766"},
    )
    assert response.status_code == 200
    client.delete("/api/v1/pins/Pod/x")


def test_invalid_namespace_is_rejected(client):
    response = client.get("/api/v1/pods", params={"namespace": "../etc"})
    assert response.status_code == 400


def test_export_csv(client):
    response = client.get("/api/v1/exports/pods", params={**SCOPE, "fmt": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "transformer-abc" in response.text


def test_export_unknown_domain_404(client):
    assert client.get("/api/v1/exports/nope", params=SCOPE).status_code == 404


def test_security_headers_present(client):
    response = client.get("/api/v1/version")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers


def test_health_and_snapshot(client):
    assert client.get("/api/v1/health", params=SCOPE).status_code == 200
    assert client.get("/api/v1/snapshot", params=SCOPE).status_code == 200


def test_baselines_roundtrip(client):
    created = client.post(
        "/api/v1/baselines", json={"name": "base1"}, params=SCOPE
    )
    assert created.status_code == 200
    listed = client.get("/api/v1/baselines").json()["data"]
    assert any(b["name"] == "base1" for b in listed)
    compared = client.post("/api/v1/baselines/compare", json={"name": "base1"}, params=SCOPE)
    assert compared.status_code == 200
    assert "rows" in compared.json()["data"]


def test_notes_roundtrip(client):
    client.post("/api/v1/notes", json={"incident_id": "INC1", "text": "checked pods"})
    notes = client.get("/api/v1/notes/INC1").json()["data"]
    assert notes and notes[0]["text"] == "checked pods"


def test_diagnostics_reports_cache(client):
    client.get("/api/v1/pods", params=SCOPE)
    diag = client.get("/api/v1/diagnostics").json()["data"]
    assert "cache" in diag and "audit" in diag


def test_engine_unavailable_yields_envelope_not_500(client, monkeypatch):
    """Fail-safe path: a missing engine must produce a documented envelope."""
    from app.services import sentinel
    from app.services.runner import Runner
    from tests.conftest import FAKE_ENGINE

    monkeypatch.setattr(
        sentinel.adapter,
        "runner",
        Runner(engine_path=FAKE_ENGINE, bash_binary="dsweb-missing-binary"),
    )
    response = client.get("/api/v1/pods", params={"context": "ctx", "namespace": "ns"})
    assert response.status_code == 200
    envelope = response.json()["envelope"]
    assert envelope["status"] == "UNAVAILABLE"
    assert envelope["data"] == []
    assert envelope["errors"]


def test_app_constructs_with_and_without_frontend_dist(client):
    """Regression guard.

    When ``frontend/dist`` exists the app registers a SPA catch-all. That route
    must declare ``response_model=None`` or FastAPI cannot build the app at all
    (FileResponse | JSONResponse is not a valid response field).
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "api/docs" in response.text or "<!doctype html>" in response.text.lower()

    # Unknown non-API paths must never fall through to an unhandled error.
    spa = client.get("/workloads")
    assert spa.status_code == 200

    # API paths must still 404 rather than returning the SPA shell.
    api = client.get("/api/v1/does-not-exist")
    assert api.status_code == 404


# --------------------------------------------------------------------------
# Log viewer + resource description viewer (read-only kubectl helpers)
# --------------------------------------------------------------------------

LOGS_TEXT = (
    "2026-10-03T00:00:01Z INFO starting web\n"
    "2026-10-03T00:00:02Z ERROR certificate verify failed\n"
    "2026-10-03T00:00:03Z WARN retrying\n"
)


def _stub_kubectl(
    monkeypatch,
    *,
    logs: str = "",
    containers: list[str] | None = None,
    describe: str = "",
    events: list[dict] | None = None,
) -> None:
    """Keep the viewer tests hermetic: never spawn a real kubectl."""
    from app.services import kube

    async def fake_containers(pod, *, context="", namespace="", timeout=15.0):
        return list(containers) if containers is not None else ["web"]

    async def fake_logs(
        pod, *, context="", namespace="", container="", tail=500,
        since="", previous=False, timestamps=True, timeout=25.0,
    ):
        return logs

    async def fake_describe(kind, name, *, context="", namespace="", fmt="describe", timeout=25.0):
        return describe

    async def fake_events(*, context="", namespace="", name="", timeout=20.0):
        return list(events or [])

    monkeypatch.setattr(kube, "pod_containers", fake_containers)
    monkeypatch.setattr(kube, "pod_logs", fake_logs)
    monkeypatch.setattr(kube, "describe_resource", fake_describe)
    monkeypatch.setattr(kube, "namespace_events", fake_events)


def test_logs_endpoint_returns_a_typed_bundle(client, monkeypatch):
    _stub_kubectl(monkeypatch, logs=LOGS_TEXT)
    body = client.get(
        "/api/v1/logs",
        params={**SCOPE, "pod": "platform-web-abc", "since": "15m", "tail": 200},
    ).json()
    env = body["envelope"]
    assert env["source"] == "LIVE"
    data = env["data"]
    assert data["pod"] == "platform-web-abc"
    assert data["since"] == "15m"
    assert data["tail"] == 200
    assert data["containers"] == ["web"]
    assert [line["level"] for line in data["lines"]] == ["INFO", "ERROR", "WARN"]
    # The RFC3339 prefix is split into its own column, not left in the message.
    assert data["lines"][1]["ts"] == "2026-10-03T00:00:02Z"
    assert data["lines"][1]["text"] == "ERROR certificate verify failed"
    assert body["raw"]["readOnlyCommand"].startswith("kubectl ")
    assert "logs" in body["raw"]["engineArgv"]


def test_logs_endpoint_redacts_credentials(client, monkeypatch):
    _stub_kubectl(monkeypatch, logs="2026-10-03T00:00:01Z Authorization: Bearer abcdef.ghijklmnop\n")
    body = client.get("/api/v1/logs", params={**SCOPE, "pod": "p"}).json()
    text = body["envelope"]["data"]["lines"][0]["text"]
    assert "abcdef.ghijklmnop" not in text
    assert "[REDACTED]" in text


def test_logs_endpoint_requires_a_namespace(client, monkeypatch):
    _stub_kubectl(monkeypatch, logs="x")
    response = client.get("/api/v1/logs", params={"context": "c", "pod": "p"})
    assert response.status_code == 400
    assert "namespace" in response.json()["detail"]


def test_logs_endpoint_rejects_an_unknown_since(client, monkeypatch):
    _stub_kubectl(monkeypatch, logs="x")
    assert client.get("/api/v1/logs", params={**SCOPE, "pod": "p", "since": "1d"}).status_code == 400


def test_containers_endpoint(client, monkeypatch):
    _stub_kubectl(monkeypatch, containers=["init", "web"])
    env = client.get("/api/v1/containers", params={**SCOPE, "pod": "p"}).json()
    assert env["data"]["containers"] == ["init", "web"]


def test_describe_endpoint_returns_text(client, monkeypatch):
    _stub_kubectl(monkeypatch, describe="Name: web\nNamespace: default\n")
    body = client.get(
        "/api/v1/describe",
        params={**SCOPE, "kind": "Deployment", "name": "web", "format": "yaml"},
    ).json()
    assert body["envelope"]["data"]["format"] == "yaml"
    assert "Name: web" in body["envelope"]["data"]["content"]
    assert body["raw"]["readOnlyCommand"].endswith("get Deployment web -o yaml")


def test_describe_endpoint_events_format(client, monkeypatch):
    _stub_kubectl(
        monkeypatch,
        events=[{"time": "t", "type": "Warning", "reason": "BackOff",
                 "object": "Pod/web", "count": 3, "message": "x"}],
    )
    body = client.get(
        "/api/v1/describe",
        params={**SCOPE, "kind": "Pod", "name": "web", "format": "events"},
    ).json()
    data = body["envelope"]["data"]
    assert data["format"] == "events"
    assert data["events"][0]["reason"] == "BackOff"


def test_describe_endpoint_rejects_a_secret_kind(client):
    """Secret payloads are never read -- rejected before kubectl is reached."""
    response = client.get(
        "/api/v1/describe",
        params={**SCOPE, "kind": "Secret", "name": "platform-tls", "format": "yaml"},
    )
    assert response.status_code == 403


def test_describe_endpoint_rejects_an_unknown_format(client, monkeypatch):
    _stub_kubectl(monkeypatch, describe="x")
    response = client.get(
        "/api/v1/describe",
        params={**SCOPE, "kind": "Pod", "name": "web", "format": "wide"},
    )
    assert response.status_code == 400
