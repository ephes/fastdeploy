from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from deploy.domain import model
from deploy.entrypoints.helper_models import StepResult


@pytest.mark.parametrize(
    "started",
    [datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None), datetime.now(timezone.utc) + timedelta(hours=1)],
)
def test_invalid_step_start_refused_without_mutation(started):
    deployment = model.Deployment(id=1, service_id=1, user="test", origin="test", started=datetime.now(timezone.utc))
    step = model.Step(name="synthetic", state="success", started=started, finished=started)
    with pytest.raises(ValueError):
        deployment.process_step(step)
    assert deployment.steps == []
    deployment.raise_recorded_events()
    assert deployment.events == []
    with pytest.raises(ValidationError):
        StepResult(**step.model_dump())


def test_step_start_normalizes_utc_and_retry_retains_server_finish():
    started = datetime.now(timezone(timedelta(hours=3))) - timedelta(minutes=1)
    deployment = model.Deployment(id=1, service_id=1, user="test", origin="test", started=datetime.now(timezone.utc))
    report = model.Step(name="synthetic", state="success", started=started, finished=started)
    [saved] = deployment.process_step(report)
    assert saved.started.tzinfo is timezone.utc
    assert saved.started == started
    assert saved.finished > started
    deployment.steps = [saved]
    finish = saved.finished
    retry = model.Step(name="synthetic", state="success", started=started.astimezone(timezone.utc), finished=started)
    assert deployment.process_step(retry) == []
    assert saved.finished == finish


def test_future_skew_boundary_is_inclusive(monkeypatch):
    now = datetime.now(timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(model, "datetime", Clock)
    boundary = now + timedelta(minutes=5)
    assert model.admitted_step_start(boundary) == boundary
    with pytest.raises(ValueError, match="future skew"):
        model.admitted_step_start(boundary + timedelta(microseconds=1))
