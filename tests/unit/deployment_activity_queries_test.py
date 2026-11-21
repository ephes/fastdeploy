"""Exercise the SQLAlchemy activity read with an isolated synthetic database."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from deploy import views
from deploy.adapters import orm, repository
from deploy.domain import model
from deploy.service_layer import handlers


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["delete", "start"])
async def test_unfinished_activity_reads_are_batched(operation, monkeypatch):
    orm.start_mappers()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = now - timedelta(days=2)
    cutoff = now - views.ORPHAN_RECONCILE_DELAY
    recent = cutoff + timedelta(microseconds=1)
    blocker_id = 111
    deployments = [
        model.Deployment(
            id=identifier,
            service_id=1,
            origin="fixture",
            user="synthetic",
            started=now if identifier == blocker_id else (None if identifier % 8 == 0 else old),
            finished=old if identifier % 8 == 1 and identifier != blocker_id else None,
        )
        for identifier in range(1, blocker_id + 1)
    ]
    steps_by_id = {}
    for deployment in deployments:
        kind = deployment.id % 8
        if kind != 2:
            steps_by_id[deployment.id] = [
                model.Step(
                    name="fixture",
                    deployment_id=deployment.id,
                    state={3: "pending", 4: "running"}.get(kind, "success"),
                    started=recent if kind == 5 else old,
                    finished=recent if kind == 6 else cutoff,
                ),
                model.Step(name="older", deployment_id=deployment.id, state="success", started=old),
            ]

    engine = create_engine("sqlite://")
    orm.metadata_obj.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(deployments)
            session.add_all(step for steps in steps_by_id.values() for step in steps)
            expected = {
                deployment.id: (
                    views.classify_unfinished_deployment(deployment, steps_by_id.get(deployment.id, []), now),
                    views.last_deployment_activity(deployment, steps_by_id.get(deployment.id, [])),
                    views.deployment_has_open_steps(steps_by_id.get(deployment.id, [])),
                )
                for deployment in deployments
                if deployment.finished is None
            }
            session.commit()

        queries, loaded = [], []

        with Session(engine) as session:

            @event.listens_for(session, "loaded_as_persistent")
            def count_loaded(session, instance):
                loaded.append(type(instance))

            @event.listens_for(engine, "before_cursor_execute")
            def count_query(conn, cursor, statement, parameters, context, executemany):
                queries.append(statement)

            class AsyncReads:
                async def execute(self, statement):
                    return session.execute(statement)

            sql = AsyncReads()
            uow = SimpleNamespace(
                deployments=repository.SqlAlchemyDeploymentRepository(sql),
                steps=repository.SqlAlchemyStepRepository(sql),
            )
            monkeypatch.setattr(handlers, "datetime", SimpleNamespace(now=lambda _: now))
            if operation == "delete":
                assert await handlers.first_active_deployment_id(1, uow, now) == blocker_id
            else:
                with pytest.raises(model.DeploymentAlreadyRunning) as refusal:
                    await handlers.finish_orphans_or_raise_if_running(1, uow)
                assert refusal.value.deployment_id == blocker_id

            assert len(queries) == 2
            assert loaded == []
            activities = [activity async for activity in views.unfinished_deployment_activity(1, uow)]
            assert [activity.id for activity in activities] == list(expected)
            for activity in activities:
                state, latest, has_open_steps = expected[activity.id]
                assert (
                    views.classify_unfinished_activity(
                        activity.started, activity.last_activity, activity.has_open_steps, now
                    )
                    == state
                )
                if activity.started is not None:
                    assert activity.last_activity == latest
                assert activity.has_open_steps == has_open_steps
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_start_rechecks_orphans_under_lock_before_staging_any_finish(in_memory_uow, monkeypatch):
    uow = in_memory_uow
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = now - views.ORPHAN_RECONCILE_DELAY
    monkeypatch.setattr(handlers, "datetime", SimpleNamespace(now=lambda _: now))
    async with uow:
        first, second = [
            model.Deployment(service_id=1, origin="fixture", user="synthetic", started=old) for _ in range(2)
        ]
        await uow.deployments.add(first)
        await uow.deployments.add(second)
        get_for_update = uow.deployments.get_for_update

        async def report_before_lock(deployment_id):
            if deployment_id == second.id:
                await uow.steps.add(
                    model.Step(name="late report", deployment_id=second.id, state="running", started=now)
                )
            return await get_for_update(deployment_id)

        monkeypatch.setattr(uow.deployments, "get_for_update", report_before_lock)

        with pytest.raises(model.DeploymentAlreadyRunning) as refusal:
            await handlers.finish_orphans_or_raise_if_running(1, uow)

        assert refusal.value.deployment_id == second.id
        assert first.finished is None and second.finished is None
        assert [step.name for step in await uow.steps.list()] == ["late report"]
