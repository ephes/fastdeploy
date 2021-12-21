from datetime import datetime, timezone

import pytest

from ..models import Step


@pytest.mark.asyncio
async def test_service_get_steps_returns_placeholder_step(service_in_db):
    steps = await service_in_db.get_steps()
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


@pytest.mark.asyncio
async def test_service_get_steps_returns_steps_from_config(service_in_db):
    steps_config_list = [{"name": "Step 1"}, {"name": "Step 2"}]
    service_in_db.data |= {"steps": steps_config_list}
    steps = await service_in_db.get_steps()
    assert len(steps) == 2
    assert steps[0].name == "Step 1"
    assert steps[1].name == "Step 2"


@pytest.mark.asyncio
async def test_service_get_steps_from_deployment_no_successful_deployment(repository, service_in_db):
    last_successful_deployment_id = await repository.get_last_successful_deployment_id(service_in_db.id)
    assert last_successful_deployment_id is None
    assert service_in_db.data.get("steps", []) == []
    steps = await service_in_db.get_steps()
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


@pytest.mark.asyncio
async def test_service_get_steps_from_deployment_only_failure_steps(repository, service_in_db, deployment_in_db):
    print("deployment service: ", deployment_in_db.service_id, service_in_db.id)
    assert service_in_db.id == deployment_in_db.service_id
    await repository.add_step(Step(name="Step 1", deployment_id=deployment_in_db.id, state="failure"))
    deployment_in_db.finished = datetime.now(timezone.utc)
    await repository.update_deployment(deployment_in_db)
    steps = await service_in_db.get_steps()
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


@pytest.mark.asyncio
async def test_service_get_steps_returns_steps_from_deployment(repository, service_in_db, deployment_in_db):
    print("deployment service: ", deployment_in_db.service_id, service_in_db.id)
    assert service_in_db.id == deployment_in_db.service_id
    step = await repository.add_step(Step(name="Step 1", deployment_id=deployment_in_db.id, state="success"))
    deployment_in_db.finished = datetime.now(timezone.utc)
    await repository.update_deployment(deployment_in_db)
    steps = await service_in_db.get_steps()
    assert len(steps) == 1
    assert steps[0].name == step.name  # steps[0] is StepBase
