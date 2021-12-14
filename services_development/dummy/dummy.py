#!/usr/bin/env python
import json

from time import sleep


for i in range(10):
    message = {"name": f"message {i}"}
    print(json.dumps(message), flush=True)
    sleep(0.5)
