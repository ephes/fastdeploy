#!/usr/bin/bash
cd ~/projects/fastdeploy/ansible
ANSIBLE_STDOUT_CALLBACK=json_cb ~/ansible_venv/bin/ansible-playbook deploy.yml
cd -
