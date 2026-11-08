"""Failed admission must roll back before any deploy task or start publication."""

import asyncio
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from deploy.domain import commands, events, model

pytestmark = pytest.mark.asyncio


class AdmissionFailure(RuntimeError):
    pass


@pytest.mark.parametrize("phase", ["flush", "step_insert", "commit"])
async def test_admission_fault_rolls_back_and_suppresses_launch(independent_bus, publisher, monkeypatch, phase):
    setup, starter = [await independent_bus() for _ in range(2)]
    service = model.Service(name="admission", data={"steps": [{"name": "first"}, {"name": "second"}]})
    async with setup.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    command = commands.StartDeployment(service_id=service.id, origin="test", user="test", context={})
    launch = Mock()
    monkeypatch.setattr("deploy.tasks.run_deploy", launch)
    fault = AdmissionFailure(phase)
    reached = []

    async def fail_flush():
        reached.append(phase)
        raise fault

    def fail_step_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO step "):
            assert conn.scalar(text("select count(*) from deployment")) == 1
            reached.append(phase)
            raise fault

    engine = starter.uow.engine.sync_engine
    if phase == "flush":
        monkeypatch.setattr(starter.uow, "flush", fail_flush)
    elif phase == "step_insert":
        event.listen(engine, "before_cursor_execute", fail_step_insert)
    else:
        async with setup.uow.engine.begin() as conn:
            await conn.execute(
                text("""
                CREATE FUNCTION admission_commit_fault() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic admission commit'; END $$
            """)
            )
            await conn.execute(
                text("""
                CREATE CONSTRAINT TRIGGER admission_commit_fault AFTER INSERT ON deployment
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION admission_commit_fault()
            """)
            )
    try:
        with pytest.raises(DBAPIError if phase == "commit" else AdmissionFailure) as error:
            await asyncio.wait_for(starter.handle(command), 5)
        if phase == "commit":
            assert "synthetic admission commit" in str(error.value)
            reached.append(phase)
        else:
            assert error.value is fault
    finally:
        if phase == "step_insert":
            event.remove(engine, "before_cursor_execute", fail_step_insert)
        elif phase == "commit":
            async with setup.uow.engine.begin() as conn:
                await conn.execute(text("DROP TRIGGER admission_commit_fault ON deployment"))
                await conn.execute(text("DROP FUNCTION admission_commit_fault()"))
    assert reached == [phase]
    launch.assert_not_called()
    assert publisher.events == []
    async with setup.uow as uow:
        assert await uow.deployments.get_by_service(service.id) == []
        assert await uow.steps.list() == []
    # A new independent request proves that neither partial state nor a lock survived.
    retry = await independent_bus()
    await asyncio.wait_for(retry.handle(command), 5)
    launch.assert_called_once()
    async with setup.uow as uow:
        [deployment] = await uow.deployments.get_by_service(service.id)
        steps = await uow.steps.get_steps_by_deployment(deployment.id)
    assert [(s.name, s.state) for s in steps] == [("first", "running"), ("second", "pending")]
    assert sum(isinstance(event, events.DeploymentStarted) for _, event in publisher.events) == 1
