from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from deploy.domain import model

pytestmark = pytest.mark.asyncio


async def test_history_pages_are_bounded_ordered_and_filtered(app, uow, service_in_db, valid_access_token_in_db):
    now = datetime.now(timezone.utc)
    async with uow:
        other = model.Service(name="fixture-other", data={})
        await uow.services.add(other)
        await uow.commit()
        ids = []
        selected_ids = []
        for i in range(113):
            service_id = service_in_db.id if i % 2 else other.id
            record = model.Deployment(
                service_id=service_id, origin="fixture", user="fixture-user", started=now, finished=now
            )
            await uow.deployments.add(record)
            await uow.commit()
            ids.append(record.id)
            if service_id == service_in_db.id:
                selected_ids.append(record.id)

    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM deployment" in statement:
            statements.append(statement)

    engine = uow.session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"authorization": f"Bearer {valid_access_token_in_db}"}
            first = (await client.get("/deployments/", headers=headers)).json()
            assert [d["id"] for d in first] == list(reversed(ids))[:50]
            maximum_page = await client.get("/deployments/", params={"limit": 200}, headers=headers)
            assert len(maximum_page.json()) == 113
            # A new deployment between pages must not shift the cursor traversal.
            async with uow:
                new_record = model.Deployment(
                    service_id=service_in_db.id, origin="fixture", user="fixture-user", started=now, finished=now
                )
                await uow.deployments.add(new_record)
                await uow.commit()
            older = await client.get(
                "/deployments/", params={"before_id": first[-1]["id"], "limit": 200}, headers=headers
            )
            assert [d["id"] for d in older.json()] == list(reversed(ids))[50:]
            cursor = None
            seen = []
            while True:
                params = {"limit": 13, "service_id": service_in_db.id}
                if cursor is not None:
                    params["before_id"] = cursor
                response = await client.get("/deployments/", params=params, headers=headers)
                assert response.status_code == 200
                page = response.json()
                assert len(page) <= 13
                if not page:
                    break
                seen.extend(d["id"] for d in page)
                cursor = page[-1]["id"]
            assert seen == [new_record.id, *reversed(selected_ids)]
            assert len(seen) == len(set(seen))
            assert (await client.get("/deployments/", params={"service_id": 999999}, headers=headers)).json() == []
            for params in ({"limit": 0}, {"limit": 201}, {"before_id": 0}, {"service_id": -1}):
                assert (await client.get("/deployments/", params=params, headers=headers)).status_code == 422
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    # The list endpoint must not load the entire history even for orphan reconciliation.
    assert statements
    assert all("LIMIT" in stmt or "deployment.finished IS NULL" in stmt for stmt in statements)
