#!/Users/jochen/.virtualenvs/fd/bin/python

import json
import os
import sys

from pathlib import Path


def cleanup_context(context):
    return context["env"]


def get_context(file_name):
    context = {}
    with open(file_name) as f:
        context = cleanup_context(json.load(f))
    return context


def main(args):
    # change into deploy directory
    deploy_directory = Path(__file__).parent
    os.chdir(deploy_directory)

    # get context from temp file + clean it up
    context = get_context(args[0])

    # set up environment
    env = os.environ.copy()
    env["ANSIBLE_STDOUT_CALLBACK"] = "json_cb"

    # FIXME: build command dynamically / better shebang
    command = "/Users/jochen/Library/Python/3.10/bin/ansible-playbook"
    # first argument gets lost dunno why
    args = ["lost", "playbook.yml", "--connection=local", "--extra-vars", json.dumps(context)]
    os.execve(command, args, env)


if __name__ == "__main__":
    main(sys.argv[1:])
