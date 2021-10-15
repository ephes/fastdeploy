#!/usr/bin/env fish

cd ~/projects/cast_hosting
ANSIBLE_STDOUT_CALLBACK=json_cb ~/.virtualenvs/ansible/bin/ansible-playbook deploy.yml
cd -
