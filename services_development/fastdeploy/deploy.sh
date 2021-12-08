#!/usr/local/bin/fish
cd ansible
ANSIBLE_STDOUT_CALLBACK=json_cb ansible-playbook deploy.yml
cd -
