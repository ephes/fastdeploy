import json

from unittest.mock import patch

import pytest

from ..tasks import DeployTask


class Response:
    def __init__(self, content):
        self.content = content

    def json(self):
        return self.content


class Client:
    put_calls = []
    post_calls = []
    current_id = 0

    async def put(self, url, json=None):
        self.put_calls.append((url, json))

    async def post(self, url, json=None):
        self.post_calls.append(json)
        content = dict(json)
        self.current_id += 1
        content["id"] = self.current_id
        return Response(content)


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
        ([{"foo": "bar"}], []),  # task with no name -> not posted
        ([{"name": "foo"}], [{"name": "foo"}]),  # task with name -> posted
    ],
)
@pytest.mark.asyncio
async def test_collect_steps(stdout, expected_steps):
    task_attrs = ["deploy_script", "collect_script", "access_token", "steps_url"]
    task_kwargs = {attr: attr for attr in task_attrs}
    task = DeployTask(**task_kwargs, client=Client())
    with patch("app.tasks.subprocess", new=CollectProc(stdout)):
        await task.collect_steps()
    assert task.client.post_calls == expected_steps
