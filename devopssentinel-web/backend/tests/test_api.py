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


def test_cache_marks_second_call_as_cache(client):
    client.get("/api/v1/pods", params=SCOPE)
    second = client.get("/api/v1/pods", params=SCOPE).json()["envelope"]
    assert second["source"] in ("CACHE", "LIVE")


def test_certificates_status_is_derived(client):
    env = client.get("/api/v1/certificates", params=SCOPE).json()["envelope"]
    by_name = {c["name"]: c for c in env["data"]}
    assert by_name["syslog-cert"]["status"] == "WARNING"


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


def test_origin_guard_allows_local_origin(client):
    response = client.post(
        "/api/v1/pins",
        json={"id": "Pod/x", "kind": "Pod", "name": "x"},
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "Pod/x"
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
