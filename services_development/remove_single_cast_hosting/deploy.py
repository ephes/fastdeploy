#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExampleContext(BaseModel):
    """
    Validate context provided by environment variable.
    """

    env: dict = {}


class AnsibleCaller(BaseSettings):
    """
    Run a deployment calling an ansible playbook.
    """

    model_config = SettingsConfigDict(env_file=None)

    context: ExampleContext
    deploy_directory: Path = Path(__file__).parent

    def run(self):
        print("context: ", self.context)
        os.chdir(self.deploy_directory)

        # set up environment
        env = os.environ.copy()
        env["ANSIBLE_STDOUT_CALLBACK"] = "json_cb"

        # FIXME: build command dynamically / better shebang
        command = "/Users/jochen/Library/Python/3.10/bin/ansible-playbook"
        # FIXME: first argument gets lost dunno why
        args = ["lost", "playbook.yml", "--connection=local", "--extra-vars", json.dumps(self.context.env)]
        os.execve(command, args, env)


def run_ansible_deployment(args):
    ansible = AnsibleCaller()  # type: ignore
    ansible.run()


if __name__ == "__main__":
    run_ansible_deployment(sys.argv[1:])
