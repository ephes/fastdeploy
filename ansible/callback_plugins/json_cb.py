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
            "state": result._result.get("state"),
            "misc": result._result,
            "failed": result.is_failed(),
            "changed": result.is_changed(),
            "skipped": result.is_skipped(),
        }
        # if result.task_name == "Add nodejs signing key - do not download if present":
        #     breakpoint()
        self.start = self.end
        self.position += 1
        return output

    def dump_result(self, result, **kwargs):
        print(json.dumps(self.build_task_output(result), sort_keys=True, indent=4))

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.tasks[task._uuid] = task.name

    def v2_runner_on_failed(self, result, ignore_errors=False):
        print("task failed!")
        self.dump_result(result, ignore_errors=ignore_errors)

    v2_runner_on_ok = dump_result
