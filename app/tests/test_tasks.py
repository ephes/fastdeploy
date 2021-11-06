import json

from unittest.mock import patch

import httpx
import pytest

from ..tasks import DeployTask


class Response:
    def __init__(self, content):
        self.content = content

    def json(self):
        return self.content


class Client:
    def __init__(self):
        self.put_calls = []
        self.post_calls = []
        self.current_id = 0
        self.raise_connect_error = False

    async def put(self, url, json=None):
        if self.raise_connect_error:
            raise httpx.ConnectError("no connection")
        self.put_calls.append(json)

    async def post(self, url, json=None):
        if self.raise_connect_error:
            raise httpx.ConnectError("no connection")
        self.post_calls.append(json)
        content = dict(json)
        self.current_id += 1
        content["id"] = self.current_id
        return Response(content)


@pytest.fixture
def task_kwargs():
    task_attrs = ["deploy_script", "collect_script", "access_token", "steps_url"]
    return {attr: attr for attr in task_attrs}


@pytest.fixture
def task(task_kwargs):
    return DeployTask(**task_kwargs, client=Client())


class CollectProc:
    PIPE = None

    def __init__(self, stdout):
        self._stdout = stdout

    def run(self, *args, **kwargs):
        return self

    @property
    def stdout(self):
        return json.dumps(self._stdout)


@pytest.mark.parametrize(
    "stdout, expected_steps",
    [
        ([], []),  # no steps collected -> no steps posted
        ([{"foo": "bar"}], []),  # step with no name -> not posted
        ([{"name": "foo"}], [{"name": "foo"}]),  # step with name -> posted
    ],
)
@pytest.mark.asyncio
async def test_collect_steps(stdout, expected_steps, task):
    with patch("app.tasks.subprocess", new=CollectProc(stdout)):
        await task.collect_steps()
    assert task.client.post_calls == expected_steps


class Subprocess:
    PIPE = None
    STDOUT = None


class DeployProc:
    PIPE = None
    STDOUT = None

    def __init__(self, stdout_lines: list):
        self._stdout_lines = stdout_lines
        self.waited_for_connection = False

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
        if line == "decodeerror":
            return line.encode("utf8")
        return json.dumps(line).encode("utf8")

    async def sleep(self, duration):
        self.waited_for_connection = True


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
@pytest.mark.asyncio
async def test_deploy_steps_post(stdout_lines, expected_steps, task):
    with patch("app.tasks.asyncio", new=DeployProc(stdout_lines)):
        await task.deploy_steps()
    actual_steps = [{"name": step["name"]} for step in task.client.post_calls]
    assert actual_steps == expected_steps


@pytest.mark.asyncio
async def test_deploy_steps_put(task):
    step = {"id": 1, "name": "foo"}
    stdout_lines = [step, None]
    with patch("app.tasks.asyncio", new=DeployProc(stdout_lines)):
        await task.deploy_steps()
    actual_steps = [{"name": step["name"], "id": step["id"]} for step in task.client.put_calls]
    assert actual_steps == [step]


def test_task_headers(task):
    assert task.headers == {"authorization": f"Bearer {task.access_token}"}


@pytest.mark.asyncio
async def test_task_sleep_on_connect_error(task):
    task.client.raise_connect_error = True
    step = {"id": 1, "name": "foo"}
    stdout_lines = [step, None]
    asyncio = DeployProc(stdout_lines)
    with patch("app.tasks.asyncio", new=asyncio):
        await task.deploy_steps()
    assert asyncio.waited_for_connection


@pytest.mark.parametrize(
    "collect_stdout, deploy_lines, steps_posted, steps_put",
    [
        # None is sentinel for last line
        ([], [None], [], []),  # no steps collected, no steps deployed -> no steps posted or put
        ([{"foo": "bar"}], [{"foo": "bar"}, None], [], []),  # no steps with names -> no steps posted or put
        (
            [{"name": "bar"}, {"name": "foo"}],  # two steps because of current step is not None coverage
            [{"name": "bar"}, {"name": "foo"}, None],
            [{"name": "bar"}, {"name": "foo"}],
            [{"id": 1, "name": "bar"}, {"id": 2, "name": "foo"}],
        ),  # happy path
    ],
)
@pytest.mark.asyncio
async def test_task_run_deploy(collect_stdout, deploy_lines, steps_put, steps_posted, task):
    with patch("app.tasks.subprocess", new=CollectProc(collect_stdout)):
        with patch("app.tasks.asyncio", new=DeployProc(deploy_lines)):
            await task.run_deploy()
    assert task.client.post_calls == steps_posted

    actual_put = []
    for step in task.client.put_calls:
        for field in ["created", "finished", "started"]:
            del step[field]  # make sure field exists
        # append twice, once for started, once for finished
        actual_put.append(step)
    expected_steps_put = []
    for step in steps_put:
        # append twice, once for started, once for finished
        expected_steps_put.append(step)
        expected_steps_put.append(step)
    assert actual_put == expected_steps_put
