import json
from datetime import datetime, timezone

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    """Output one JSON observation for each terminal task callback."""

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "json_cb"

    def __init__(self):
        super().__init__()
        self.tasks = {}
        self.position = 0
        self.start = datetime.now(timezone.utc)
        self.end = None

    def build_task_output(self, result, *, state, outcome, ignore_errors=False):
        self.end = datetime.now(timezone.utc)
        no_log = result._task.no_log or result._result.get("_ansible_no_log", False)
        # Select the safe payload before extracting messages or serializing.
        data = {"censored": "output hidden due to no_log"} if no_log else result._result
        misc = json.loads(self._dump_results(data))
        output = {
            "position": self.position,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "name": "censored task" if no_log else self.tasks.get(result._task._uuid, result._task.get_name()),
            "state": state,
            "outcome": outcome,
            "ignore_errors": ignore_errors,
            "error_message": misc.get("msg", ""),
            "misc": misc,
        }
        self.start = self.end
        self.position += 1
        return output

    def dump_result(self, result, **kwargs):
        # One line per observation: runners parse stdout as JSON Lines.
        print(json.dumps(self.build_task_output(result, **kwargs)))

    def v2_playbook_on_task_start(self, task, is_conditional):  # noqa: ARG002 (Ansible callback signature)
        self.tasks[task._uuid] = task.name

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.dump_result(result, ignore_errors=ignore_errors, state="failure", outcome="failed")

    def v2_runner_on_ok(self, result):
        self.dump_result(result, state="success", outcome="ok")

    def v2_runner_on_skipped(self, result):
        self.dump_result(result, state="success", outcome="skipped")

    def v2_runner_on_unreachable(self, result):
        self.dump_result(result, state="failure", outcome="unreachable")
