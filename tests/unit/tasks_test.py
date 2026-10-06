import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from deploy.domain.model import Step
from deploy.tasks import DeploymentContext, DeployTask

pytestmark = pytest.mark.asyncio


class Response:
    def __init__(self, content):
        self.content = content

    def json(self):
        return self.content

    def raise_for_status(self):
        pass


class Client:
    def __init__(self):
        self.post_calls = []
        self.current_id = 0
        self.raise_connect_error = False

    async def put(self, url, json=None):
        return Response({})

    async def post(self, url, json=None):
        if self.raise_connect_error:
            raise httpx.HTTPStatusError(
                "connection error",
                response=httpx.Response(status_code=502),
                request=httpx.Request(method="post", url=url),
            )
        self.post_calls.append(json)
        content = dict(json)
        self.current_id += 1
        content["id"] = self.current_id
        return Response(content)


@pytest.fixture
def task_kwargs():
    task_attrs = ["deploy_script", "access_token", "steps_url", "deployment_finish_url"]
    kwargs = {attr: attr for attr in task_attrs}
    kwargs["path_for_deploy"] = "/tmp/deploy"
    return kwargs


@pytest.fixture
def task(task_kwargs):
    context = DeploymentContext(env={"env": {"foo": "bar"}})
    return DeployTask(**task_kwargs, context=context, client=Client())


class Subprocess:
    PIPE = None
    STDOUT = None


class DeployProc:
    PIPE = None
    STDOUT = None

    def __init__(
        self,
        stdout_lines: list,
        returncode: int = 0,
        exit_after_line: int | None = None,
    ):
        self._stdout_lines = stdout_lines
        self._lines_read = 0
        self._exit_after_line = exit_after_line
        self.waited_for_connection = False
        self.returncode = returncode

    @property
    def subprocess(self):
        return self

    @property
    def stdout(self):
        return self

    async def create_subprocess_shell(self, *args, **kwargs):
        return self

    async def readline(self):
        if (line := self._stdout_lines.pop(0)) is None:
            return ""
        self._lines_read += 1
        # Simulate process exiting while buffered data remains
        if self._exit_after_line is not None and self._lines_read >= self._exit_after_line:
            self.returncode = 0
        if line == "decodeerror":
            return line.encode("utf8")
        return json.dumps(line).encode("utf8")

    async def sleep(self, duration):
        self.waited_for_connection = True

    async def wait(self):
        """Mock wait method for process completion."""
        return self.returncode


@pytest.mark.parametrize(
    "stdout_lines, expected_steps",
    [
        # None is sentinel for last line
        ([None], []),  # no steps deployed -> no steps posted
        ([{"foo": "bar"}, None], []),  # step with no name -> not posted
        ([{"name": "foo"}, None], [{"name": "foo"}]),  # step with name -> posted
        (["decodeerror", None], []),  # return no json line -> no step posted
    ],
)
async def test_deploy_steps_post(stdout_lines, expected_steps, task):
    with patch("deploy.tasks.asyncio", new=DeployProc(stdout_lines)):
        await task.deploy_steps()
    actual_steps = [{"name": step["name"]} for step in task.client.post_calls]
    assert actual_steps == expected_steps


@pytest.mark.parametrize(
    "predefined_steps, deploy_lines, steps_posted",
    [
        # None is sentinel for last line
        ([], [None], []),  # no steps collected, no steps deployed -> no steps posted or put
        ([{"foo": "bar"}], [{"foo": "bar"}, None], []),  # no steps with names -> no steps posted
        (
            [
                {"name": "bar", "id": 1},
                {"name": "foo", "id": 2},
            ],  # two steps because of current step is not None coverage
            # set state to make finish_step start next step
            [{"name": "bar", "state": "success"}, {"name": "foo"}, None],
            [{"id": None, "name": "bar"}, {"id": None, "name": "foo"}],
        ),  # happy path
    ],
)
async def test_task_run_deploy(predefined_steps, deploy_lines, steps_posted, task):
    # task.steps = [Step(**predefined) for predefined in predefined_steps if "name" in predefined]
    with patch("deploy.tasks.asyncio", new=DeployProc(deploy_lines)):
        await task.run_deploy()
    post_calls = []
    for step in task.client.post_calls:
        base_step = {field: step[field] for field in ["id", "name"]}
        post_calls.append(base_step)
    assert post_calls == steps_posted


async def test_task_run_deploy_marks_failure_on_nonzero_exit(task):
    with (
        patch("deploy.tasks.asyncio", new=DeployProc([None], returncode=126)),
        pytest.raises(RuntimeError, match="deploy script exited with code 126"),
    ):
        await task.run_deploy()

    assert any(step["name"] == "failed step" for step in task.client.post_calls)


async def test_deploy_steps_drains_stdout_after_process_exits(task):
    """
    Regression test: ensure all buffered stdout is processed even when
    the subprocess exits quickly.

    This tests the fix for a race condition where the loop checked
    proc.returncode after readline() but before processing the data,
    causing output to be discarded when the process exited while
    buffered data remained in stdout.
    """
    stdout_lines = [
        {"name": "step1", "state": "running"},
        {"name": "step2", "state": "running"},
        {"name": "step3", "state": "running"},
        {"name": "step4", "state": "success"},
        None,  # EOF sentinel
    ]
    # Process exits after reading line 1, but lines 2-4 are still buffered
    mock_proc = DeployProc(stdout_lines, exit_after_line=1)

    with patch("deploy.tasks.asyncio", new=mock_proc):
        await task.deploy_steps()

    # All 4 steps should be posted, not just the first one
    posted_names = [step["name"] for step in task.client.post_calls]
    assert posted_names == ["step1", "step2", "step3", "step4"]


class FlakyClient(Client):
    """Fails the first post/put calls with the given errors, then succeeds."""

    def __init__(self, post_errors=(), put_errors=()):
        super().__init__()
        self.post_errors = list(post_errors)
        self.put_errors = list(put_errors)
        self.post_attempts = 0
        self.put_attempts = 0

    async def post(self, url, json=None):
        self.post_attempts += 1
        if self.post_errors:
            raise self.post_errors.pop(0)
        return await super().post(url, json=json)

    async def put(self, url, json=None):
        self.put_attempts += 1
        if self.put_errors:
            raise self.put_errors.pop(0)
        return await super().put(url, json=json)


def connect_error():
    return httpx.ConnectError("connection refused", request=httpx.Request("POST", "http://api/steps/"))


def status_error(status_code):
    request = httpx.Request("POST", "http://api/steps/")
    return httpx.HTTPStatusError(
        "status error", request=request, response=httpx.Response(status_code=status_code, request=request)
    )


@pytest.fixture
def no_sleep():
    sleeps = []

    async def fake_sleep(duration):
        sleeps.append(duration)

    with patch("deploy.tasks.asyncio.sleep", new=fake_sleep):
        yield sleeps


def make_task(task_kwargs, client):
    return DeployTask(**task_kwargs, context=DeploymentContext(), client=client)


async def test_send_step_retries_transport_errors_with_backoff(task_kwargs, no_sleep):
    client = FlakyClient(post_errors=[connect_error(), connect_error()])
    task = make_task(task_kwargs, client)

    await task.finish_step({"name": "foo", "state": "success"})

    assert client.post_attempts == 3
    assert [step["name"] for step in client.post_calls] == ["foo"]
    assert no_sleep == [task.sleep_on_fail, task.sleep_on_fail * 2]


async def test_send_step_retries_server_errors(task_kwargs, no_sleep):
    client = FlakyClient(post_errors=[status_error(502)])
    task = make_task(task_kwargs, client)

    await task.finish_step({"name": "foo", "state": "success"})

    assert [step["name"] for step in client.post_calls] == ["foo"]


async def test_send_step_does_not_retry_client_errors(task_kwargs, no_sleep, capsys):
    client = FlakyClient(post_errors=[status_error(422)])
    task = make_task(task_kwargs, client)

    await task.finish_step({"name": "foo", "state": "success"})

    assert client.post_attempts == 1
    assert client.post_calls == []
    assert "dropped step 'foo'" in capsys.readouterr().err


async def test_send_step_logs_dropped_step_after_last_attempt(task_kwargs, no_sleep, capsys):
    client = FlakyClient(post_errors=[connect_error() for _ in range(10)])
    task = make_task(task_kwargs, client)

    assert await task.send_step(task.steps_url, Step(name="foo")) is False

    assert client.post_attempts == task.attempts
    err = capsys.readouterr().err
    assert "dropped step 'foo'" in err
    assert "access_token" not in err


async def test_deploy_steps_keeps_draining_stdout_after_failed_post(task_kwargs, no_sleep):
    client = FlakyClient(post_errors=[connect_error() for _ in range(4)])
    task = make_task(task_kwargs, client)
    stdout_lines = [{"name": "step1"}, {"name": "step2"}, {"name": "step3"}, None]
    proc = DeployProc(stdout_lines)

    with patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell):
        await task.deploy_steps()

    assert proc._lines_read == 3
    assert [step["name"] for step in client.post_calls] == ["step2", "step3"]


async def test_deploy_steps_keeps_draining_stdout_after_invalid_step(task, capsys):
    stdout_lines = [{"name": "step1"}, {"name": "step2"}, None]
    proc = DeployProc(stdout_lines)

    with (
        patch("deploy.tasks.asyncio", new=proc),
        patch.object(DeployTask, "finish_step", side_effect=[ValueError("boom"), None]) as finish_step,
    ):
        await task.deploy_steps()

    assert finish_step.call_count == 2
    assert "could not report step 'step1'" in capsys.readouterr().err


async def test_run_deploy_finishes_after_step_post_failures(task_kwargs, no_sleep):
    # all attempts for step1 fail, the failed step is reported
    client = FlakyClient(post_errors=[connect_error() for _ in range(4)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([{"name": "step1"}, None], returncode=1)

    with (
        patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell),
        pytest.raises(RuntimeError, match="exited with code 1"),
    ):
        await task.run_deploy()

    assert [step["name"] for step in client.post_calls] == ["failed step"]
    assert client.put_attempts == 1


async def test_finish_deployment_is_retried(task_kwargs, no_sleep):
    client = FlakyClient(put_errors=[connect_error(), status_error(503)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([None])

    with patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell):
        await task.run_deploy()

    assert client.put_attempts == 3


async def test_finish_deployment_failure_does_not_replace_original_error(task_kwargs, no_sleep, capsys):
    client = FlakyClient(put_errors=[connect_error() for _ in range(100)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([None], returncode=2)

    with (
        patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell),
        pytest.raises(RuntimeError, match="exited with code 2"),
    ):
        await task.run_deploy()

    assert client.put_attempts == task.finish_attempts
    assert [step["name"] for step in client.post_calls] == ["failed step"]
    assert "could not finish deployment" in capsys.readouterr().err


async def test_failed_step_report_gets_finish_attempts(task_kwargs, no_sleep):
    client = FlakyClient(post_errors=[connect_error() for _ in range(5)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([None], returncode=2)

    with (
        patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell),
        pytest.raises(RuntimeError, match="exited with code 2"),
    ):
        await task.run_deploy()

    assert [step["name"] for step in client.post_calls] == ["failed step"]
    assert client.put_attempts == 1


async def test_deployment_not_finished_when_failure_cannot_be_reported(task_kwargs, no_sleep, capsys):
    """Finishing would remove the open steps and make the failed deployment look successful."""
    client = FlakyClient(post_errors=[connect_error() for _ in range(100)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([None], returncode=2)

    with (
        patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell),
        pytest.raises(RuntimeError, match="exited with code 2"),
    ):
        await task.run_deploy()

    assert client.put_attempts == 0
    assert "not finishing the deployment" in capsys.readouterr().err


async def test_cancelled_deployment_reports_failure_before_finishing(task):
    with (
        patch.object(DeployTask, "deploy_steps", side_effect=asyncio.CancelledError()),
        pytest.raises(asyncio.CancelledError),
    ):
        await task.run_deploy()

    [failed_step] = task.client.post_calls
    assert failed_step["name"] == "failed step"
    assert failed_step["message"] == "deployment failed: CancelledError"


async def test_deploy_steps_skips_json_that_is_not_an_object(task):
    proc = DeployProc([[], "a string", 42, {"name": "step1"}, None])

    with patch("deploy.tasks.asyncio", new=proc):
        await task.deploy_steps()

    assert [step["name"] for step in task.client.post_calls] == ["step1"]


async def test_finish_deployment_failure_is_raised_without_original_error(task_kwargs, no_sleep):
    client = FlakyClient(put_errors=[connect_error() for _ in range(100)])
    task = make_task(task_kwargs, client)
    proc = DeployProc([None])

    with (
        patch("deploy.tasks.asyncio.create_subprocess_shell", new=proc.create_subprocess_shell),
        pytest.raises(httpx.ConnectError),
    ):
        await task.run_deploy()


@pytest.mark.parametrize(
    "error_message, expected",
    [
        (["first", "second"], '["first", "second"]'),
        ({"msg": "failed"}, '{"msg": "failed"}'),
        (42, "42"),
        (None, ""),
        ("", ""),
        ("plain", "plain"),
    ],
)
async def test_finish_step_coerces_error_message_to_text(error_message, expected, task):
    await task.finish_step({"name": "foo", "state": "failure", "error_message": error_message})

    assert task.client.post_calls[0]["message"] == expected
