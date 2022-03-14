import json

from unittest.mock import patch

import httpx
import pytest

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

    async def post(self, url, json={}):
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
