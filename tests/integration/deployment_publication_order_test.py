"""Committed request order does not guarantee websocket publication order."""

import asyncio

import pytest

from deploy.domain import commands, events, model


@pytest.mark.asyncio
async def test_two_buses_can_publish_finish_before_start(independent_bus, publisher, monkeypatch):
    setup, starter, finisher = [await independent_bus() for _ in range(3)]
    async with setup.uow as uow:
        service = model.Service(name="synthetic-order", data={"steps": []})
        await uow.services.add(service)
        await uow.commit()

    def fake_launch(deployment, _service):
        deployment.record(events.DeploymentStarted)

    monkeypatch.setattr(model.Deployment, "start_deployment_task", fake_launch)
    waiting, release = asyncio.Event(), asyncio.Event()
    started = []

    async def delay_start(event):
        started.append(event)
        waiting.set()
        await release.wait()

    starter.event_handlers[events.DeploymentStarted].insert(0, delay_start)
    task = asyncio.create_task(
        starter.handle(
            commands.StartDeployment(service_id=service.id, user="synthetic", origin="frontend", context={})
        )
    )
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        await finisher.handle(commands.FinishDeployment(deployment_id=started[0].id))
    finally:
        release.set()
        await asyncio.wait_for(task, 5)
    published = [event for _, event in publisher.events if isinstance(event, events.DeploymentStarted)]
    assert [type(event) for event in published] == [events.DeploymentFinished, events.DeploymentStarted]
    assert published[0].finished is not None
    assert published[1].finished is None
    async with setup.uow as uow:
        assert (await uow.deployments.get(started[0].id)).finished == published[0].finished
