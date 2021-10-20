#!/usr/bin/env python

import json

from time import sleep


def main():
    for i in range(100):
        message = json.dumps({"name": f"message number {i}"})
        line = f"{message}"
        print(line, flush=True)
        sleep(0.5)


if __name__ == "__main__":
    main()
