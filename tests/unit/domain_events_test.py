import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deploy.domain import events

STARTED = datetime(2026, 11, 1, tzinfo=timezone.utc)
FINISHED = datetime(2026, 11, 1, 0, 1, tzinfo=timezone.utc)
NAMED_ENTITY = {"id": 1, "name": "synthetic"}
STEP = {
    "id": 1,
    "name": "synthetic",
    "state": "running",
    "deployment_id": 1,
    "message": "",
    "started": STARTED,
    "finished": None,
}
DEPLOYMENT = {"id": 1, "service_id": 1, "origin": "fixture", "user": "synthetic", "started": STARTED}


@pytest.mark.parametrize(
    ("event_class", "fields", "wire_type"),
    [
        (events.AuthenticationSucceeded, {}, "authentication"),
        (events.AuthenticationFailed, {}, "authentication"),
        (events.UserCreated, NAMED_ENTITY, "user"),
        (events.ServiceCreated, NAMED_ENTITY, "service"),
        (events.ServiceUpdated, NAMED_ENTITY, "service"),
        (events.ServiceDeleted, NAMED_ENTITY, "service"),
        (events.StepProcessed, STEP, "step"),
        (events.StepDeleted, STEP, "step"),
        (events.DeploymentStarted, {**DEPLOYMENT, "finished": None}, "deployment"),
        (events.DeploymentFinished, {**DEPLOYMENT, "finished": FINISHED}, "deployment"),
    ],
)
def test_produced_event_enforces_its_wire_type(event_class, fields, wire_type):
    event = event_class(**fields)
    assert event.type == wire_type
    assert event_class(**fields, type=wire_type) == event
    serialized = event.model_dump_json()
    assert json.loads(serialized)["type"] == wire_type
    assert event_class.model_validate_json(serialized) == event

    conflicting_type = "service" if wire_type == "deployment" else "deployment"
    with pytest.raises(ValidationError) as error:
        event_class(**fields, type=conflicting_type)
    assert [(entry["loc"], entry["type"]) for entry in error.value.errors()] == [(("type",), "literal_error")]
