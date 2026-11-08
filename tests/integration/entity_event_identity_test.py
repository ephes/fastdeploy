"""Event ownership survives flush, mutable fields and equivalent ORM instances."""

from datetime import datetime, timedelta, timezone

import pytest

from deploy.domain import events, model

pytestmark = pytest.mark.asyncio


async def test_two_unsaved_entities_keep_their_events(independent_bus):
    bus = await independent_bus()
    async with bus.uow as uow:
        service = model.Service(name="sample")
        await uow.services.add(service)
        await uow.flush()
        now = datetime.now(timezone.utc)
        deployments = [
            model.Deployment(service_id=service.id, origin="fixture", user="sample", started=now) for _ in range(2)
        ]
        for deployment in deployments:
            deployment.record(events.DeploymentStarted)
            await uow.deployments.add(deployment)
        assert len(uow.deployments.seen) == 2
        await uow.flush()
        steps = [model.Step(name="identical", deployment_id=deployments[0].id) for _ in range(2)]
        for step in steps:
            step.process()
            await uow.steps.add(step)
        assert len(uow.steps.seen) == 2
        await uow.commit()
    emitted = list(uow.collect_new_events())
    assert {e.id for e in emitted if type(e) is events.DeploymentStarted} == {d.id for d in deployments}
    assert {e.id for e in emitted if isinstance(e, events.StepProcessed)} == {s.id for s in steps}
    assert len(emitted) == 4
    assert list(uow.collect_new_events()) == []


async def test_mutation_and_reload_keep_each_object_once(independent_bus):
    bus = await independent_bus()
    now = datetime.now(timezone.utc)
    async with bus.uow as uow:
        service = model.Service(name="sample")
        await uow.services.add(service)
        await uow.flush()
        deployment = model.Deployment(service_id=service.id, origin="fixture", user="sample", started=now)
        await uow.deployments.add(deployment)
        await uow.flush()
        step = model.Step(name="step", deployment_id=deployment.id, started=now)
        await uow.steps.add(step)
        await uow.commit()
        for entity, repo in ((deployment, uow.deployments), (step, uow.steps)):
            entity.started += timedelta(seconds=1)
            await repo.add(entity)
            assert len(repo.seen) == 1
        await uow.commit()
        step.process()
        deployment.record(events.DeploymentStarted)
        uow.session.expunge(step)
        uow.session.expunge(deployment)
        reloaded_step = await uow.steps.get(step.id)
        reloaded_deployment = await uow.deployments.get(deployment.id)
        assert reloaded_step == step and reloaded_step is not step
        assert reloaded_deployment == deployment and reloaded_deployment is not deployment
        reloaded_step.process()
        reloaded_deployment.finished = now + timedelta(seconds=2)
        reloaded_deployment.record(events.DeploymentFinished)
        await uow.steps.add(reloaded_step)
        await uow.deployments.add(reloaded_deployment)
        await uow.commit()
    emitted = list(uow.collect_new_events())
    assert len([e for e in emitted if isinstance(e, events.StepProcessed)]) == 2
    assert len([e for e in emitted if type(e) is events.DeploymentStarted]) == 1
    assert len([e for e in emitted if isinstance(e, events.DeploymentFinished)]) == 1
    assert list(uow.collect_new_events()) == []
