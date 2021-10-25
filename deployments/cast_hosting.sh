#!/usr/local/bin/fish
cd ~/projects/cast_hosting/ansible
ANSIBLE_STDOUT_CALLBACK=json_cb ~/.virtualenvs/ansible/bin/ansible-playbook deploy.yml
cd -
