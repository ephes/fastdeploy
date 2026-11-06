"""Repeated CLI bootstrap against isolated PostgreSQL preserves the existing user."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_repeated_bootstrap_preserves_user_and_password(database):
    spec = importlib.util.spec_from_file_location(
        "bootstrap_commands", Path(__file__).resolve().parents[2] / "commands.py"
    )
    commands_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(commands_module)
    created = await commands_module.createuser_async("sample-repeat", "synthetic-original-hash")
    assert created.name == "sample-repeat"
    assert await commands_module.createuser_async("sample-repeat", "synthetic-replacement-hash") is None

    bus = await commands_module.get_bus_for_cli()
    try:
        async with bus.uow as uow:
            users = await uow.users.list()
            assert len(users) == 1
            assert users[0].name == "sample-repeat"
            assert users[0].password == "synthetic-original-hash"
    finally:
        await bus.uow.close()
