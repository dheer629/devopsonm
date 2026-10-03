"""Runner tests: argv construction, JSON parsing, timeout, redaction."""

from __future__ import annotations

import sys

import pytest

from app.services.runner import Runner
from app.services.sentinel import SentinelAdapter
from tests.conftest import FAKE_ENGINE


def test_build_argv_is_read_only_guarded(fake_runner):
    argv = fake_runner.build_argv(["--resources"])
    assert argv[0] == sys.executable
    assert "--no-color" in argv
    with pytest.raises(PermissionError):
        fake_runner.build_argv(["--resources", "delete"])


async def test_run_returns_json_envelope(fake_runner):
    result = await fake_runner.run(
        ["--context", "ctx-a", "--namespace", "ns-a", "--resources", "--json"],
        operation="workloads.resources",
    )
    assert result.exit_status == 0
    envelope = SentinelAdapter.parse_json(result.stdout)
    assert envelope is not None
    assert envelope.tool_version == "4.2.2"
    assert envelope.context == "ctx-a"
    assert envelope.namespace == "ns-a"
    assert any("transformer" in line for line in envelope.lines)


async def test_run_redacts_secrets_from_stdout(fake_runner):
    result = await fake_runner.run(
        ["--context", "ctx", "--namespace", "ns", "--capabilities", "--json"],
        operation="system.capabilities",
    )
    assert "eyJhbGciOiJIUzI1NiJ9" not in result.stdout


async def test_run_times_out_and_reports(fake_runner):
    result = await fake_runner.run(["--sleep"], timeout=0.5, operation="system.self_test")
    assert result.timed_out is True
    assert result.exit_status == 124


async def test_missing_engine_reports_failure():
    runner = Runner(engine_path=FAKE_ENGINE.parent / "does-not-exist.py", bash_binary=sys.executable)
    result = await runner.run(["--resources"], operation="workloads.resources")
    assert result.exit_status != 0
    assert "No such file" in result.stderr or result.exit_status == 127


async def test_missing_interpreter_reports_unavailable():
    runner = Runner(engine_path=FAKE_ENGINE, bash_binary="dsweb-definitely-not-a-real-binary")
    result = await runner.run(["--resources"], operation="workloads.resources")
    assert result.exit_status == 127
    assert "not found" in result.error


def test_parse_json_tolerates_noise():
    payload = '{"schema_version":"1.0","lines":["a"]}'
    assert SentinelAdapter.parse_json("warning\n" + payload) is not None
    assert SentinelAdapter.parse_json("not json") is None
    assert SentinelAdapter.parse_json("") is None
