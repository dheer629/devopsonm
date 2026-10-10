"""The origin allow-list must contain the origin the app is served on.

Regression: ``DSWEB_PORT=8766`` (the WSL run) and ``--port N`` moved the page to
an origin the allow-list did not contain, so *every* state-changing request was
answered ``403 origin not allowed`` while every read succeeded. The page looked
connected and only the buttons failed, which is exactly the shape of defect that
survives a fixture-backed suite: the tests never asked the backend to trust the
address it had been told to serve on.
"""

from __future__ import annotations

from app.config import Settings
from app.security import origin_allowed


def test_the_serving_origin_is_always_allowed():
    for host in ("127.0.0.1", "localhost"):
        for port in (8765, 8766, 9000):
            settings = Settings(host=host, port=port, allowed_origins=[])
            assert origin_allowed(f"http://{host}:{port}", settings.allowed_origins), (
                host,
                port,
            )


def test_a_custom_port_does_not_strand_the_page():
    """The reported defect: the WSL run on 8766 could not POST anything."""
    settings = Settings(host="127.0.0.1", port=8766, allowed_origins=[])
    assert origin_allowed("http://127.0.0.1:8766", settings.allowed_origins)
    assert origin_allowed("http://localhost:8766", settings.allowed_origins)


def test_a_wildcard_bind_still_trusts_loopback():
    """`DSWEB_HOST=0.0.0.0` (the container) is reached on loopback by the operator."""
    settings = Settings(host="0.0.0.0", port=8766, allowed_origins=[])
    assert settings.allowed_origins == ["http://127.0.0.1:8766", "http://localhost:8766"]


def test_a_named_host_is_trusted_without_inventing_loopback():
    settings = Settings(host="sentinel.local", port=8766, allowed_origins=[])
    assert settings.allowed_origins == ["http://sentinel.local:8766"]


def test_the_serving_origin_is_not_duplicated():
    settings = Settings(
        host="127.0.0.1", port=8765, allowed_origins=["http://127.0.0.1:8765"]
    )
    assert settings.allowed_origins == ["http://127.0.0.1:8765", "http://localhost:8765"]


def test_an_explicit_allow_list_keeps_its_other_origins():
    """`DSWEB_ALLOWED_ORIGINS` narrows everything else; the bind is still added."""
    settings = Settings(
        host="127.0.0.1",
        port=8766,
        allowed_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    )
    assert origin_allowed("http://127.0.0.1:5173", settings.allowed_origins)
    assert origin_allowed("http://127.0.0.1:8766", settings.allowed_origins)


def test_the_allow_list_never_becomes_a_wildcard():
    for host in ("127.0.0.1", "0.0.0.0", "sentinel.local", "::"):
        settings = Settings(host=host, port=9000, allowed_origins=[])
        assert "*" not in settings.allowed_origins
        assert not origin_allowed("http://evil.example", settings.allowed_origins)
        assert not origin_allowed("http://evil.example:9000", settings.allowed_origins)
