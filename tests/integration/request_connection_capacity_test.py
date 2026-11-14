import asyncio

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from deploy import bootstrap
from deploy.entrypoints.fastapi_app import lifespan

pytestmark = pytest.mark.asyncio

HELD = 20  # more than a default pool's 5 + 10 overflow


async def test_long_lived_bus_holders_do_not_starve_new_requests(database):
    """Requests holding their bus connection (like websockets) must not block other requests."""
    application = FastAPI(lifespan=lifespan)
    release, all_held = asyncio.Event(), asyncio.Event()
    holding = []

    @application.get("/hold")
    async def hold(bus=Depends(bootstrap.get_bus)):
        holding.append(bus)
        if len(holding) == HELD:
            all_held.set()
        await release.wait()
        return {"ok": True}

    @application.get("/probe")
    async def probe(bus=Depends(bootstrap.get_bus)):
        return {"ok": True}

    transport = ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        held = [asyncio.create_task(client.get("/hold")) for _ in range(HELD)]
        try:
            await asyncio.wait_for(all_held.wait(), 10)
            response = await asyncio.wait_for(client.get("/probe"), 5)
            assert response.status_code == 200
        finally:
            release.set()
            results = await asyncio.gather(*held)
        assert all(result.status_code == 200 for result in results)
