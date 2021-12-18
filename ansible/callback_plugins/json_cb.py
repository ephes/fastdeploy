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

    def get_error_message(self, result):
        if "msg" in result:
            return result["msg"]
        return ""

    def build_task_output(self, result, state="unkown", ignore_errors=False):
        self.end = datetime.now()
        error_message = self.get_error_message(result._result)
        output = {
            "position": self.position,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "name": self.tasks[result._task._uuid],
            "state": state,
            "error_message": error_message,
            "misc": result._result,
        }
        self.start = self.end
        self.position += 1
        return output

    def dump_result(self, result, **kwargs):
        # print(json.dumps(self.build_task_output(result, **kwargs), sort_keys=True, indent=4))
        # Dont pretty print if running from tasks.py, because it will break the json
        print(json.dumps(self.build_task_output(result, **kwargs)))

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.tasks[task._uuid] = task.name

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.dump_result(result, ignore_errors=ignore_errors, state="failure")

    def v2_runner_on_ok(self, result, ignore_errors=False):
        self.dump_result(result, ignore_errors=ignore_errors, state="success")
