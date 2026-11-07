"""Exercise the retained stdout callback without running an Ansible playbook."""

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.domain.model import REPORTED_STEP_STATES

CALLBACK_PATH = Path(__file__).resolve().parents[2] / "ansible/callback_plugins/json_cb.py"


@pytest.fixture
def callback(tmp_path, monkeypatch):
    monkeypatch.setenv("ANSIBLE_LOCAL_TEMP", str(tmp_path))
    spec = importlib.util.spec_from_file_location("fastdeploy_json_callback", CALLBACK_PATH)
    callback_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(callback_module)
    return callback_module.CallbackModule()


TERMINALS = [
    ("v2_runner_on_ok", {}, "success", "ok"),
    ("v2_runner_on_failed", {}, "failure", "failed"),
    ("v2_runner_on_failed", {"ignore_errors": True}, "failure", "failed"),
    ("v2_runner_on_skipped", {}, "success", "skipped"),
    ("v2_runner_on_unreachable", {}, "failure", "unreachable"),
]


def task_result(*, task_no_log=False, result_no_log=False):
    from ansible.playbook.task import Task

    task = Task()
    task.name = "synthetic task"
    task.no_log = task_no_log
    data = {
        "msg": "private-sentinel",
        "stdout": "private-sentinel",
        "nested": {"private-sentinel": ["private-sentinel"]},
        "_ansible_no_log": result_no_log,
    }
    return SimpleNamespace(_task=task, _result=data)


@pytest.mark.parametrize("method,kwargs,state,outcome", TERMINALS)
@pytest.mark.parametrize("task_no_log,result_no_log", [(True, False), (False, True), (True, True)])
def test_no_log_hides_all_result_content(callback, method, kwargs, state, outcome, task_no_log, result_no_log, capsys):
    result = task_result(task_no_log=task_no_log, result_no_log=result_no_log)
    # A templated task label can contain the same sensitive value.
    result._task.name = "private-sentinel"
    callback.v2_playbook_on_task_start(result._task, False)
    getattr(callback, method)(result, **kwargs)
    captured = capsys.readouterr()
    assert "private-sentinel" not in captured.out + captured.err
    output = json.loads(captured.out)
    assert output["misc"]["censored"]
    assert output["error_message"] == ""
    assert output["name"] == "censored task"
    assert output["outcome"] == outcome
    assert output["ignore_errors"] == kwargs.get("ignore_errors", False)
    assert output["position"] == 0
    assert output["state"] == state
    assert datetime.fromisoformat(output["end"]) >= datetime.fromisoformat(output["start"])
    assert result._result["msg"] == "private-sentinel"  # serialization must not mutate Ansible's data


def test_terminal_callbacks_emit_one_coherent_observation_each(callback, capsys):
    result = task_result()
    callback.v2_playbook_on_task_start(result._task, False)
    for method, kwargs, _state, _outcome in TERMINALS:
        getattr(callback, method)(result, **kwargs)
    captured = capsys.readouterr()
    assert captured.err == ""
    outputs = [json.loads(line) for line in captured.out.splitlines()]
    assert len(outputs) == len(TERMINALS)
    for position, (output, (_, kwargs, state, outcome)) in enumerate(zip(outputs, TERMINALS, strict=True)):
        assert output["position"] == position
        assert output["name"] == "synthetic task"
        assert output["state"] == state
        assert output["state"] in REPORTED_STEP_STATES
        assert output["outcome"] == outcome
        assert output["ignore_errors"] == kwargs.get("ignore_errors", False)
        assert output["error_message"] == "private-sentinel"
        assert output["misc"]["stdout"] == "private-sentinel"
        assert output["misc"]["nested"] == {"private-sentinel": ["private-sentinel"]}
        assert datetime.fromisoformat(output["end"]) >= datetime.fromisoformat(output["start"])
        if position:
            assert output["start"] == outputs[position - 1]["end"]


@pytest.mark.parametrize("method,kwargs,state,outcome", TERMINALS)
def test_handler_terminal_result_without_regular_task_start(callback, method, kwargs, state, outcome, capsys):
    from ansible.playbook.handler import Handler

    handler = Handler()
    handler.name = "synthetic restart handler"
    result = SimpleNamespace(_task=handler, _result={"msg": "handler result"})
    callback.v2_playbook_on_handler_task_start(handler)
    getattr(callback, method)(result, **kwargs)
    output = json.loads(capsys.readouterr().out)
    assert output["name"] == "synthetic restart handler"
    assert output["state"] == state
    assert output["outcome"] == outcome
    assert output["ignore_errors"] == kwargs.get("ignore_errors", False)
    assert output["position"] == 0
