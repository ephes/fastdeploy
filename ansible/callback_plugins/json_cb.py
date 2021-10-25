import json

from datetime import datetime

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "json_cb"

    def __init__(self):
        self.tasks = {}
        self.position = 0
        self.start = datetime.now()
        self.end = None

    def build_task_output(self, result):
        self.end = datetime.now()
        output = {
            "position": self.position,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "name": self.tasks[result._task._uuid],
            "changed": result._result.get("changed", False),
            "state": result._result.get("state"),
            "misc": result._result,
        }
        self.start = self.end
        self.position += 1
        return output

    def dump_result(self, result, **kwargs):
        print(json.dumps(self.build_task_output(result)))

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.tasks[task._uuid] = task.name

    v2_runner_on_ok = dump_result
    v2_runner_on_failed = dump_result
