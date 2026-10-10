"""Security tests: redaction, validation, read-only guard, origin checks."""

from __future__ import annotations

import json

import pytest

from app.security import (
    assert_read_only,
    origin_allowed,
    redact_text,
    validate_context,
    validate_kind,
    validate_name,
    validate_tail,
)


def test_redact_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    assert "eyJhbGciOiJIUzI1NiJ9" not in redact_text(text)
    assert "[REDACTED]" in redact_text(text)


def test_redact_url_credentials():
    text = "postgres://admin:s3cr3t@db.internal:5432/app"
    out = redact_text(text)
    assert "s3cr3t" not in out
    assert "db.internal" in out


def test_redact_private_key_block():
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA\n"
        "-----END RSA PRIVATE KEY-----\n"
        "done"
    )
    out = redact_text(text)
    assert "MIIEowIBAAKCAQEA" not in out
    assert "[REDACTED PRIVATE KEY]" in out


def test_redact_key_value_password():
    assert "hunter2" not in redact_text("password=hunter2")


def test_redact_keeps_json_documents_parseable():
    """Regression: pretty-printed ``--json`` must survive redaction.

    A line-at-a-time sweep used to replace a whole structural line (any line
    that merely mentioned TOKEN) and leave unparseable JSON behind. The adapter
    then reported "engine produced no machine-readable output" and the UI showed
    an empty or blank page.
    """
    payload = {
        "schema_version": "1.0",
        "lines": [
            "Splunk\tNOT_CONFIGURED\tset SPLUNK_HEC_TOKEN=abcdef",
            "cert-manager\tNOT_PROBED",
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        ],
    }
    text = json.dumps(payload, indent=2)
    out = redact_text(text)
    parsed = json.loads(out)  # must not raise
    assert parsed["lines"][1] == "cert-manager\tNOT_PROBED"
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "[REDACTED]" in out


def test_redact_still_treats_plain_text_line_wise():
    text = "kubectl AVAILABLE\nAuthorization: Bearer eyJhbGciOiJIUzI1NiJ9.x.y"
    out = redact_text(text)
    assert "kubectl AVAILABLE" in out
    assert "eyJhbGciOiJIUzI1NiJ9" not in out


def test_redact_keeps_tab_table_rows_intact():
    """A sensitive CELL must not collapse a TAB-separated engine table row.

    Regression: whole-row redaction replaced ``name<TAB>Opaque<TAB>…<TAB>password``
    with a single ``[REDACTED]`` token. ``extract_tables`` treats a one-cell line as
    the end of the table, so every later Secret row silently disappeared from
    ``/api/v1/secrets`` (only the first Secret was ever listed).
    """
    row = "platform-postgres\tOpaque\t2026-10-04T10:44:21Z\t1\tpassword"
    cells = redact_text(row).split("\t")
    assert len(cells) == 5
    assert cells[:4] == ["platform-postgres", "Opaque", "2026-10-04T10:44:21Z", "1"]
    assert cells[4] == "[REDACTED]"

    # A row with no sensitive cell is passed through untouched.
    following = "platform-tls\tkubernetes.io/tls\t2026-10-04T10:44:21Z\t2\ttls.crt tls.key"
    assert redact_text(following) == following

    # The same guarantee holds on the JSON (``--json``) path.
    payload = json.dumps({"lines": [row, following]})
    lines = json.loads(redact_text(payload))["lines"]
    assert len(lines) == 2
    assert lines[1] == following
    assert lines[0].split("\t")[0] == "platform-postgres"


def test_read_only_guard_blocks_mutation_verbs():
    with pytest.raises(PermissionError):
        assert_read_only(["get", "pods", "delete", "pod/x"])
    with pytest.raises(PermissionError):
        assert_read_only(["apply", "-f", "x.yaml"])
    # read-only commands pass
    assert_read_only(["get", "pods", "-n", "default"])


def test_validate_name_rejects_injection():
    assert validate_name("transformer-abc") == "transformer-abc"
    for bad in ("../etc/passwd", "a;rm -rf /", "$(whoami)", "UPPER", "with space", ""):
        with pytest.raises(ValueError):
            validate_name(bad)


def test_validate_context_allows_real_contexts():
    assert validate_context("vcluster-docker_dev") == "vcluster-docker_dev"
    assert validate_context("pny9-11-ccd3-oidc") == "pny9-11-ccd3-oidc"
    with pytest.raises(ValueError):
        validate_context("bad context; rm -rf /")


def test_validate_kind():
    assert validate_kind("Deployment") == "Deployment"
    with pytest.raises(ValueError):
        validate_kind("Deployment; rm")


def test_validate_tail_bounds():
    assert validate_tail(500) == 500
    with pytest.raises(ValueError):
        validate_tail(0)
    with pytest.raises(ValueError):
        validate_tail(10_000_000)


def test_origin_allowed():
    allowed = ["http://127.0.0.1:8765"]
    assert origin_allowed(None, allowed)
    assert origin_allowed("http://127.0.0.1:8765", allowed)
    assert not origin_allowed("http://evil.example", allowed)
