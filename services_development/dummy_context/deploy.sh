#!/bin/bash
echo "running deploy script"
pwd
cd services_development/dummy_context
echo "huh?"
echo $1 > /tmp/foo
ANSIBLE_STDOUT_CALLBACK=json_cb /Users/jochen/Library/Python/3.10/bin/ansible-playbook playbook.yml --connection=local --extra-vars "${1}"
cd -
