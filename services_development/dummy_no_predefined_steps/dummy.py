#!/usr/bin/env python
import json

from time import sleep


for i in range(5):
    message = {"name": f"message {i}", "state": "success"}
    print(json.dumps(message), flush=True)
    sleep(0.5)
