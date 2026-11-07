"""Exercise configuration and the production request boundary without real services."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from deploy.tasks import DeploymentContext, DeployTask

pytestmark = pytest.mark.asyncio


@pytest.fixture
def kwargs():
    return {
        "deployment_id": "synthetic",
        "deploy_script": "/synthetic/script",
        "access_token": "synthetic",
        "steps_url": "http://test/steps",
        "deployment_finish_url": "http://test/finish",
        "context": DeploymentContext(),
        "path_for_deploy": "/synthetic",
    }


@pytest.mark.parametrize("field", ["attempts", "finish_attempts"])
@pytest.mark.parametrize("value", [0, -1, 9, 1000000, 1.5, True, False])
async def test_bad_attempt_configuration_precedes_subprocess(kwargs, field, value):
    with patch("deploy.tasks.asyncio.create_subprocess_exec") as spawn, pytest.raises(ValidationError):
        task = DeployTask(**kwargs, **{field: value})
        await task.deploy_steps()
    spawn.assert_not_called()


@pytest.mark.parametrize("value", [-1, 11, float("inf"), float("-inf"), float("nan"), True])
async def test_bad_backoff_configuration_precedes_subprocess(kwargs, value):
    with patch("deploy.tasks.asyncio.create_subprocess_exec") as spawn, pytest.raises(ValidationError):
        task = DeployTask(**kwargs, sleep_on_fail=value)
        await task.deploy_steps()
    spawn.assert_not_called()


@pytest.mark.parametrize("field, value", [("attempts", "0"), ("finish_attempts", "1000000"), ("sleep_on_fail", "nan")])
async def test_invalid_environment_configuration(kwargs, monkeypatch, field, value):
    monkeypatch.setenv(field.upper(), value)
    with pytest.raises(ValidationError):
        DeployTask(**kwargs)


@pytest.mark.parametrize("field, value", [("attempts", 0), ("finish_attempts", -1), ("sleep_on_fail", float("nan"))])
async def test_invalid_retry_assignment_is_refused(kwargs, field, value):
    task = DeployTask(**kwargs)
    with pytest.raises(ValidationError):
        setattr(task, field, value)


@pytest.mark.parametrize("attempts", [0, -1, 9, 1000000, True, False, 1.5, "2"])
async def test_helper_override_refuses_invalid_attempts_before_client_or_sleep(kwargs, attempts):
    task = DeployTask(**kwargs, client=AsyncMock())
    with patch("deploy.tasks.asyncio.sleep") as sleep, pytest.raises(ValidationError):
        await task.request_with_retries("post", task.steps_url, attempts=attempts)
    task.client.stream.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize("value", [-1, 11, float("nan"), float("inf"), True])
async def test_helper_revalidates_backoff_before_client_or_sleep(kwargs, value):
    # model_copy deliberately bypasses normal validation, exercising the helper boundary.
    task = DeployTask(**kwargs, client=AsyncMock()).model_copy(update={"sleep_on_fail": value})
    with patch("deploy.tasks.asyncio.sleep") as sleep, pytest.raises(ValidationError):
        await task.request_with_retries("post", task.steps_url, attempts=1)
    task.client.stream.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize("attempts, backoff", [(1, 0), (4, 3), (8, 10)])
async def test_valid_retry_boundaries_preserve_requests_and_exponential_delays(kwargs, attempts, backoff):
    calls = []
    sleeps = []

    async def handle(request):
        calls.append(request)
        if len(calls) < attempts:
            raise httpx.ConnectError("synthetic failure", request=request)
        return httpx.Response(204)  # no body needed

    async def sleep(delay):
        sleeps.append(delay)

    # A 204 response is created with an unconsumed stream, as on the wire.
    class EmptyBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            if False:
                yield b""

    async def streaming_handle(request):
        response = await handle(request)
        return httpx.Response(response.status_code, stream=EmptyBody())

    async with httpx.AsyncClient(transport=httpx.MockTransport(streaming_handle)) as client:
        task = DeployTask(**kwargs, attempts=attempts, finish_attempts=attempts, sleep_on_fail=backoff, client=client)
        with patch.object(asyncio, "sleep", sleep):
            await task.finish_deployment()
    assert len(calls) == attempts
    assert sleeps == [backoff * 2**index for index in range(attempts - 1)]
