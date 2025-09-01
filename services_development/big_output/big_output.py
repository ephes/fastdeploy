#!/usr/bin/env python
import json
from time import sleep

for i in range(2):
    message = {"name": f"message {i}", "state": "success"}
    if i == 1:
        message["foo"] = "y" * 100000
    print(json.dumps(message), flush=True)
    sleep(0.5)
