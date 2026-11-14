"""Synthetic process groups and HTTP streams; no host services or deployment scripts."""

import asyncio
import signal
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from deploy import tasks
from deploy.tasks import DeploymentContext, DeployTask

pytestmark = pytest.mark.asyncio


@pytest.fixture
def task():
    return DeployTask(
        deployment_id="synthetic",
        deploy_script="/synthetic/script",
        access_token="synthetic",
        steps_url="http://test/steps",
        deployment_finish_url="http://test/finish",
        context=DeploymentContext(),
        path_for_deploy="/synthetic",
        attempts=1,
        finish_attempts=1,
        sleep_on_fail=0,
        deployment_max_runtime_seconds=0.03,
    )


@pytest.mark.parametrize("mode", ["silent", "chatty", "wait"])
async def test_runtime_expiry_cleans_group_and_config_before_failure_report(task, monkeypatch, tmp_path, mode):
    alive = {100, 101}  # script and descendant owned by the fake group
    signals = []
    requests = []
    reads = []
    waited = []

    class Process:
        pid = 100

        @property
        def stdout(self):
            return self

        async def readuntil(self, separator):
            reads.append(True)
            if mode == "silent":
                await asyncio.Event().wait()
            if mode == "wait":
                raise asyncio.IncompleteReadError(b"", None)
            await asyncio.sleep(0)
            return b"not JSON\n"

        async def wait(self):
            waited.append(True)
            if alive:
                await asyncio.Event().wait()
            return -9

    async def spawn(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        assert list(tmp_path.glob("*.json"))
        return Process()

    def killpg(pgid, sig):
        assert pgid == 100
        if not alive:
            raise ProcessLookupError
        if sig:
            signals.append(sig)
        if sig == signal.SIGKILL:
            alive.clear()

    def handle(request):
        assert not alive
        assert not list(tmp_path.glob("*.json"))
        requests.append(request)
        return httpx.Response(200, stream=Body([]))

    monkeypatch.setattr(tasks, "DEPLOY_STOP_TIMEOUT", 0.001)
    monkeypatch.setattr(tasks.os, "killpg", killpg)
    monkeypatch.setattr(tasks.asyncio, "create_subprocess_exec", spawn)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        task.client = client
        with pytest.raises(RuntimeError, match=r"runtime limit of 0\.03 seconds"):
            await asyncio.wait_for(task.run_deploy(), timeout=1)

    assert reads and waited
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert [r.method for r in requests] == ["POST", "PUT"]
    assert b"runtime limit of 0.03 seconds" in requests[0].content


async def test_timely_process_succeeds_with_confirmed_cleanup(task, monkeypatch, tmp_path):
    class Process:
        @property
        def stdout(self):
            return self

        async def readuntil(self, separator):
            raise asyncio.IncompleteReadError(b"", None)

        async def wait(self):
            return 0

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(tasks.asyncio, "create_subprocess_exec", spawn)
    with patch.object(DeployTask, "stop_deploy_process", return_value=True) as stop:
        await task.deploy_steps()
    stop.assert_awaited_once()
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 86401])
async def test_invalid_runtime_is_rejected(task, value):
    with pytest.raises(ValidationError):
        DeployTask(**(task.model_dump() | {"deployment_max_runtime_seconds": value}))


class Body(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closed = True


async def test_report_oversize_body_stops_reading_and_closes(task):
    body = Body([b"x" * 1024] * 100)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=body))) as client:
        task.client = client
        with pytest.raises(httpx.ReadError, match="byte limit"):
            await task.request_with_retries("post", task.steps_url, attempts=1)
    assert body.reads == 5
    assert body.closed


@pytest.mark.parametrize("phase", ["headers", "body"])
async def test_report_elapsed_budget_retries_and_closes(task, monkeypatch, phase):
    monkeypatch.setattr(tasks, "REPORT_RESPONSE_TIMEOUT_SECONDS", 0.025)
    bodies = []
    calls = []

    async def handle(request):
        calls.append(request)
        if len(calls) == 1:
            if phase == "headers":
                await asyncio.sleep(0.2)
            body = Body([b"x"] * 100, delay=0.005)
        else:
            body = Body([])
        bodies.append(body)
        return httpx.Response(200, stream=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        task.client = client
        await task.request_with_retries("put", task.deployment_finish_url, attempts=2)
    assert len(calls) == 2
    assert all(body.closed for body in bodies)
    if phase == "body":
        assert 0 < bodies[0].reads < 100


async def test_report_timeout_exhaustion_is_an_http_failure(task, monkeypatch):
    monkeypatch.setattr(tasks, "REPORT_RESPONSE_TIMEOUT_SECONDS", 0.01)
    body = Body([b"x"] * 100, delay=0.005)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=body))) as client:
        task.client = client
        assert await task.finish_step({"name": "synthetic", "state": "success"}) is False
    assert body.closed


@pytest.mark.parametrize("status, attempts", [(200, 1), (422, 1), (503, 2)])
async def test_report_status_and_empty_body_retry_contract(task, status, attempts):
    bodies = []

    def handle(request):
        body = Body([])
        bodies.append(body)
        return httpx.Response(status if len(bodies) == 1 else 200, stream=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        task.client = client
        if status == 422:
            with pytest.raises(httpx.HTTPStatusError):
                await task.request_with_retries("post", task.steps_url, attempts=2)
        else:
            await task.request_with_retries("post", task.steps_url, attempts=2)
    assert len(bodies) == attempts
    assert all(body.closed for body in bodies)


@pytest.mark.parametrize("status", [422, 503])
async def test_error_status_precedes_oversized_or_dripping_body(task, status):
    bodies = []

    def handle(request):
        body = Body([b"x" * 8192] * 100, delay=0.1)
        bodies.append(body)
        return httpx.Response(status if len(bodies) == 1 else 200, stream=body if len(bodies) == 1 else Body([]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        task.client = client
        if status == 422:
            with pytest.raises(httpx.HTTPStatusError) as error:
                await task.request_with_retries("post", task.steps_url, attempts=2)
            assert error.value.response.status_code == 422
        else:
            await task.request_with_retries("post", task.steps_url, attempts=2)
    assert len(bodies) == (1 if status == 422 else 2)
    assert bodies[0].closed
    assert bodies[0].reads == 0
