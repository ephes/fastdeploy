#!/usr/bin/env python
import json

from time import sleep


for i in range(3):
    message = {"name": f"message {i}", "state": "success"}
    print(json.dumps(message), flush=True)
    sleep(0.5)

message = {"name": "message 3", "state": "failure"}
print(json.dumps(message), flush=True)
