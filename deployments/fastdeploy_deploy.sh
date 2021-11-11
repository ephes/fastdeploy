#!/usr/bin/bash
cd /home/deploy/ansible
ANSIBLE_STDOUT_CALLBACK=json_cb /home/deploy/ansible_venv/bin/ansible-playbook deploy.yml
cd -
