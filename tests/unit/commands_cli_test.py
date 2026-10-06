"""Tests for the "issueservicetoken" command of commands.py (argument handling and output)."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from deploy.auth import ServiceTokenIssueRefused
from deploy.domain import model

COMMANDS_PATH = Path(__file__).resolve().parents[2] / "commands.py"


@pytest.fixture(scope="module")
def commands_module():
    spec = importlib.util.spec_from_file_location("fastdeploy_commands", COMMANDS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner():
    return CliRunner()


def test_issueservicetoken_prints_only_token_on_stdout(commands_module, runner, monkeypatch):
    calls = []
    record = model.ServiceToken(
        jti="abc123",
        service="echoport",
        origin="ops-control",
        user="deploy",
        issued_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        expires_at=datetime(2027, 1, 4, tzinfo=timezone.utc),
    )

    async def fake_issue(service, origin, user, days):
        calls.append((service, origin, user, days))
        return "the.jwt.token", record

    monkeypatch.setattr(commands_module, "_issueservicetoken", fake_issue)
    result = runner.invoke(
        commands_module.cli,
        ["issueservicetoken", "--service", "echoport", "--user", "deploy", "--days", "90", "--origin", "ops-control"],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("echoport", "ops-control", "deploy", 90)]
    assert result.stdout == "the.jwt.token\n"
    assert "abc123" in result.stderr
    assert "2027-01-04" in result.stderr


def test_issueservicetoken_default_origin(commands_module, runner, monkeypatch):
    calls = []

    async def fake_issue(service, origin, user, days):
        calls.append(origin)
        raise ServiceTokenIssueRefused("unknown service 'x'")

    monkeypatch.setattr(commands_module, "_issueservicetoken", fake_issue)
    runner.invoke(commands_module.cli, ["issueservicetoken", "--service", "x", "--user", "u", "--days", "1"])
    assert calls == ["cli"]


def test_issueservicetoken_refusal_exits_1_without_stdout(commands_module, runner, monkeypatch):
    async def fake_issue(service, origin, user, days):
        raise ServiceTokenIssueRefused("days must be between 1 and 90 (SERVICE_TOKEN_MAX_EXPIRE_DAYS)")

    monkeypatch.setattr(commands_module, "_issueservicetoken", fake_issue)
    result = runner.invoke(commands_module.cli, ["issueservicetoken", "--service", "s", "--user", "u", "--days", "91"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "between 1 and 90" in result.stderr


@pytest.mark.parametrize("missing", ["--service", "--user", "--days"])
def test_issueservicetoken_requires_options(commands_module, runner, missing):
    args = {"--service": "s", "--user": "u", "--days": "1"}
    del args[missing]
    argv = ["issueservicetoken"] + [part for pair in args.items() for part in pair]
    result = runner.invoke(commands_module.cli, argv)
    assert result.exit_code == 2
