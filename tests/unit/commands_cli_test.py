"""Database-free tests for account/token CLI dispatch, output and resource cleanup."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, NoResultFound
from typer.testing import CliRunner

from deploy.auth import ServiceTokenIssueRefused, verify_password
from deploy.domain import commands, events, model

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


@pytest.fixture
def token_records():
    return [
        model.ServiceToken(
            jti="fixture-active",
            service="sample-service",
            user="sample-user",
            origin="sample-cli",
            issued_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        model.ServiceToken(
            jti="fixture-revoked",
            service="other-service",
            user="other-user",
            origin="sample-api",
            issued_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            expires_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
            revoked_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
    ]


def test_listservicetokens_inventory(commands_module, runner, monkeypatch, token_records):
    inventory = AsyncMock(return_value=token_records)
    monkeypatch.setattr(commands_module, "_listservicetokens", inventory)
    # Keep Rich's real output but prevent terminal-width-dependent line wrapping.
    monkeypatch.setenv("COLUMNS", "240")
    result = runner.invoke(commands_module.cli, ["listservicetokens"])
    assert result.exit_code == 0, result.output
    inventory.assert_awaited_once_with()
    assert result.stdout.splitlines() == [
        "fixture-active  service=sample-service user=sample-user origin=sample-cli "
        "expires=2026-02-01T00:00:00+00:00 active",
        "fixture-revoked  service=other-service user=other-user origin=sample-api "
        "expires=2026-02-02T00:00:00+00:00 revoked 2026-01-03T00:00:00+00:00",
    ]


def test_listservicetokens_empty(commands_module, runner, monkeypatch):
    inventory = AsyncMock(return_value=[])
    monkeypatch.setattr(commands_module, "_listservicetokens", inventory)
    result = runner.invoke(commands_module.cli, ["listservicetokens"])
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    inventory.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_listservicetokens_helper_closes_uow(commands_module, monkeypatch, token_records, fails):
    failure = RuntimeError("synthetic repository failure")
    repository = SimpleNamespace(list=AsyncMock(return_value=token_records, side_effect=failure if fails else None))
    uow = MagicMock(service_tokens=repository, close=AsyncMock())
    uow.__aenter__.return_value = uow
    factory = AsyncMock(return_value=SimpleNamespace(uow=uow))
    monkeypatch.setattr(commands_module, "get_bus_for_cli", factory)
    if fails:
        with pytest.raises(RuntimeError, match="synthetic repository failure"):
            await commands_module._listservicetokens()
    else:
        assert await commands_module._listservicetokens() is token_records
    factory.assert_awaited_once_with()
    repository.list.assert_awaited_once_with()
    uow.__aenter__.assert_awaited_once_with()
    uow.__aexit__.assert_awaited_once()
    uow.close.assert_awaited_once_with()


def test_revokeservicetoken_dispatch(commands_module, runner, monkeypatch, token_records):
    revoke = AsyncMock(return_value=token_records[1])
    monkeypatch.setattr(commands_module, "_revokeservicetoken", revoke)
    monkeypatch.setenv("COLUMNS", "240")
    result = runner.invoke(commands_module.cli, ["revokeservicetoken", "fixture-revoked"])
    assert result.exit_code == 0, result.output
    revoke.assert_awaited_once_with("fixture-revoked")
    assert result.stdout == (
        "revoked service token fixture-revoked (service other-service, user other-user) at 2026-01-03 00:00:00+00:00\n"
    )


def test_revokeservicetoken_unknown_jti(commands_module, runner, monkeypatch):
    revoke = AsyncMock(side_effect=model.ServiceTokenNotFound("fixture-missing"))
    monkeypatch.setattr(commands_module, "_revokeservicetoken", revoke)
    result = runner.invoke(commands_module.cli, ["revokeservicetoken", "fixture-missing"])
    assert result.exit_code == 1
    assert "service token fixture-missing not found" in result.stdout
    revoke.assert_awaited_once_with("fixture-missing")


def test_revokeservicetoken_requires_jti(commands_module, runner, monkeypatch):
    revoke = AsyncMock()
    monkeypatch.setattr(commands_module, "_revokeservicetoken", revoke)
    result = runner.invoke(commands_module.cli, ["revokeservicetoken"])
    assert result.exit_code == 2
    revoke.assert_not_called()


@pytest.mark.parametrize("override, expected", [(None, 43), ("17", 17)])
def test_purgeservicetokens_retention(commands_module, runner, monkeypatch, override, expected):
    monkeypatch.setattr(commands_module.settings, "service_token_retention_days", 43)
    purge = AsyncMock(return_value=7)
    monkeypatch.setattr(commands_module, "_purgeservicetokens", purge)
    argv = ["purgeservicetokens"]
    if override is not None:
        argv += ["--older-than-days", override]
    result = runner.invoke(commands_module.cli, argv)
    assert result.exit_code == 0, result.output
    purge.assert_awaited_once_with(expected)
    assert result.stdout == f"deleted 7 service token record(s) expired or revoked more than {expected} days ago\n"


@pytest.mark.parametrize("days", ["0", "-1"])
def test_purgeservicetokens_rejects_nonpositive_retention(commands_module, runner, monkeypatch, days):
    purge = AsyncMock()
    monkeypatch.setattr(commands_module, "_purgeservicetokens", purge)
    result = runner.invoke(commands_module.cli, ["purgeservicetokens", "--older-than-days", days])
    assert result.exit_code == 2
    purge.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize(
    "helper, argument, expected_command",
    [
        ("_revokeservicetoken", "fixture-jti", commands.RevokeServiceToken(jti="fixture-jti")),
        ("_purgeservicetokens", 19, commands.PurgeServiceTokens(retention_days=19)),
    ],
)
async def test_token_mutation_helpers_dispatch_and_close(
    commands_module, monkeypatch, helper, argument, expected_command, fails
):
    failure = RuntimeError("synthetic bus failure")
    bus = SimpleNamespace(
        handle=AsyncMock(return_value=7, side_effect=failure if fails else None),
        uow=SimpleNamespace(close=AsyncMock()),
    )
    factory = AsyncMock(return_value=bus)
    monkeypatch.setattr(commands_module, "get_bus_for_cli", factory)
    if fails:
        with pytest.raises(RuntimeError, match="synthetic bus failure"):
            await getattr(commands_module, helper)(argument)
    else:
        assert await getattr(commands_module, helper)(argument) == 7
    factory.assert_awaited_once_with()
    bus.handle.assert_awaited_once_with(expected_command)
    bus.uow.close.assert_awaited_once_with()


def test_createuser_environment_credentials(commands_module, runner, monkeypatch):
    password_hash = commands_module.get_password_hash("synthetic-environment-password")
    monkeypatch.setenv("INITIAL_USER_NAME", "sample-bootstrap")
    monkeypatch.setenv("INITIAL_PASSWORD_HASH", password_hash)
    create = AsyncMock(return_value=events.UserCreated(id=1, name="sample-bootstrap"))
    prompt = MagicMock(side_effect=AssertionError("environment credentials must avoid prompts"))
    monkeypatch.setattr(commands_module, "createuser_async", create)
    monkeypatch.setattr(commands_module.Prompt, "ask", prompt)
    result = runner.invoke(commands_module.cli, ["createuser"])
    assert result.exit_code == 0, result.output
    create.assert_awaited_once_with("sample-bootstrap", password_hash)
    prompt.assert_not_called()
    assert "created:" in result.stdout
    assert password_hash not in result.output
    assert "synthetic-environment-password" not in result.output


def test_createuser_interactive_credentials_are_hashed(commands_module, runner, monkeypatch):
    monkeypatch.delenv("INITIAL_USER_NAME", raising=False)
    monkeypatch.delenv("INITIAL_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("USER", "sample-default")
    prompt = MagicMock(side_effect=["sample-interactive", "synthetic-interactive-password"])
    monkeypatch.setattr(commands_module.Prompt, "ask", prompt)
    create = AsyncMock(return_value=events.UserCreated(id=1, name="sample-interactive"))
    monkeypatch.setattr(commands_module, "createuser_async", create)
    result = runner.invoke(commands_module.cli, ["createuser"])
    assert result.exit_code == 0, result.output
    assert prompt.call_count == 2
    assert prompt.call_args_list[0].args == ("Enter username",)
    assert prompt.call_args_list[0].kwargs == {"default": "sample-default"}
    assert prompt.call_args_list[1].args == ("Enter password",)
    assert prompt.call_args_list[1].kwargs == {"password": True}
    create.assert_awaited_once()
    username, credential_digest = create.await_args.args
    assert username == "sample-interactive"
    assert credential_digest != "synthetic-interactive-password"
    assert verify_password("synthetic-interactive-password", credential_digest)
    assert "created:" in result.stdout
    assert credential_digest not in result.output
    assert "synthetic-interactive-password" not in result.output


def test_createuser_failure_exits_nonzero(commands_module, runner, monkeypatch):
    monkeypatch.setenv("INITIAL_USER_NAME", "sample-bootstrap")
    monkeypatch.setenv("INITIAL_PASSWORD_HASH", "synthetic-prehashed-value")
    create = AsyncMock(side_effect=RuntimeError("synthetic creation failure"))
    monkeypatch.setattr(commands_module, "createuser_async", create)
    result = runner.invoke(commands_module.cli, ["createuser"])
    assert result.exit_code == 1, result.output
    create.assert_awaited_once_with("sample-bootstrap", "synthetic-prehashed-value")
    assert "failed to create user sample-bootstrap" in result.stdout
    assert "synthetic creation failure" in result.stdout
    assert "created:" not in result.stdout
    assert "synthetic-prehashed-value" not in result.output


def test_createuser_existing_user_succeeds_without_replacing_password(commands_module, runner, monkeypatch):
    monkeypatch.setenv("INITIAL_USER_NAME", "sample-existing")
    monkeypatch.setenv("INITIAL_PASSWORD_HASH", "synthetic-new-hash")
    existing = model.User(name="sample-existing", password="synthetic-original-hash")
    uow = MagicMock(users=SimpleNamespace(get=AsyncMock(return_value=existing)), close=AsyncMock())
    uow.__aenter__.return_value = uow
    bus = SimpleNamespace(
        uow=uow,
        event_handlers={events.UserCreated: []},
        handle=AsyncMock(side_effect=IntegrityError(None, None, RuntimeError("synthetic duplicate username"))),
    )
    monkeypatch.setattr(commands_module, "get_bus_for_cli", AsyncMock(return_value=bus))
    result = runner.invoke(commands_module.cli, ["createuser"])
    assert result.exit_code == 0, result.output
    assert "user sample-existing already exists" in result.stdout
    assert "created:" not in result.stdout
    assert "synthetic-new-hash" not in result.output
    assert "synthetic-original-hash" not in result.output
    uow.users.get.assert_awaited_once_with("sample-existing")
    bus.handle.assert_not_called()
    assert existing.password == "synthetic-original-hash"
    uow.close.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", [None, "lookup", "creation"])
async def test_createuser_helper_dispatch_and_cleanup(commands_module, monkeypatch, failure_stage):
    lookup_error = RuntimeError("synthetic lookup failure") if failure_stage == "lookup" else NoResultFound()
    uow = MagicMock(users=SimpleNamespace(get=AsyncMock(side_effect=lookup_error)), close=AsyncMock())
    uow.__aenter__.return_value = uow
    created = events.UserCreated(id=1, name="sample-new")
    bus = SimpleNamespace(uow=uow, event_handlers={events.UserCreated: []})

    async def handle(command):
        if failure_stage == "creation":
            raise RuntimeError("synthetic creation failure")
        for handler in bus.event_handlers[events.UserCreated]:
            await handler(created)

    bus.handle = AsyncMock(side_effect=handle)
    monkeypatch.setattr(commands_module, "get_bus_for_cli", AsyncMock(return_value=bus))
    if failure_stage:
        with pytest.raises(RuntimeError, match=f"synthetic {failure_stage} failure"):
            await commands_module.createuser_async("sample-new", "synthetic-hash")
    else:
        assert await commands_module.createuser_async("sample-new", "synthetic-hash") is created
    uow.users.get.assert_awaited_once_with("sample-new")
    if failure_stage == "lookup":
        bus.handle.assert_not_called()
    else:
        bus.handle.assert_awaited_once_with(commands.CreateUser(username="sample-new", password_hash="synthetic-hash"))
    uow.close.assert_awaited_once_with()


@pytest.mark.parametrize("length", [255, 256])
def test_cli_unicode_origin_storage_limit(commands_module, runner, monkeypatch, length):
    from deploy.service_layer.unit_of_work import InMemoryUnitOfWork

    uow = InMemoryUnitOfWork()

    async def setup_bus():
        await uow.users.add(model.User(name="sample"))
        await uow.services.add(model.Service(name="sample"))
        return SimpleNamespace(uow=uow)

    uow.close = AsyncMock()
    monkeypatch.setattr(commands_module, "get_bus_for_cli", setup_bus)
    cleanup = AsyncMock(wraps=uow.service_tokens.delete_stale)
    monkeypatch.setattr(uow.service_tokens, "delete_stale", cleanup)
    result = runner.invoke(
        commands_module.cli,
        ["issueservicetoken", "--service", "sample", "--user", "sample", "--days", "1", "--origin", "界" * length],
    )
    assert result.exit_code == (0 if length == 255 else 1), result.output
    if length == 256:
        assert result.stdout == ""
        assert len(result.stderr) < 250
        cleanup.assert_not_called()
        assert not uow.committed
