"""
Concurrent revocations of the same service token against the real database.

Each revocation runs on its own connection/transaction (like concurrent API
requests), so this exercises the database row lock on the token record.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from deploy.adapters import repository
from deploy.domain import commands, model
from tests.integration.single_flight_concurrency_test import make_bus

pytestmark = pytest.mark.asyncio

CONCURRENT_REVOCATIONS = 4


@pytest.fixture
def widen_read_write_window(monkeypatch):
    """
    Yield to the event loop between reading the token record and writing the
    revocation, so that without a lock every revocation would read NULL.
    """
    original = repository.SqlAlchemyServiceTokenRepository.get_by_jti

    async def slow_get_by_jti(self, jti, for_update=False):
        result = await original(self, jti, for_update=for_update)
        await asyncio.sleep(0.2)
        return result

    monkeypatch.setattr(repository.SqlAlchemyServiceTokenRepository, "get_by_jti", slow_get_by_jti)


async def test_concurrent_revocations_keep_first_revoked_at(
    database, publisher, services_filesystem, widen_read_write_window
):
    setup_bus = await make_bus(publisher, services_filesystem)
    now = datetime.now(timezone.utc)
    record = model.ServiceToken(
        jti="concurrent", service="svc", origin="test", user="user", issued_at=now, expires_at=now + timedelta(days=1)
    )
    async with setup_bus.uow as uow:
        await uow.service_tokens.add(record)
        await uow.commit()

    buses = [await make_bus(publisher, services_filesystem) for _ in range(CONCURRENT_REVOCATIONS)]
    cmd = commands.RevokeServiceToken(jti="concurrent")
    try:
        results = await asyncio.wait_for(asyncio.gather(*(bus.handle(cmd) for bus in buses)), timeout=30)
    finally:
        for bus in buses:
            await bus.uow.close()

    try:
        async with setup_bus.uow as uow:
            stored = await uow.service_tokens.get_by_jti("concurrent")
        assert stored is not None
        assert {result.revoked_at for result in results} == {stored.revoked_at}
    finally:
        await setup_bus.uow.close()
