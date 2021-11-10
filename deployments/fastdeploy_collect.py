# import sys
import json

from pathlib import Path

import yaml


playbook_path = Path(__file__).parent.parent / "ansible/deploy.yml"
with playbook_path.open("r") as f:
    parsed = yaml.safe_load(f)
steps = parsed[0]["tasks"]
steps.insert(0, {"name": "Gathering Facts"})
print(json.dumps(steps))
# print("hello world: ", sys.executable)
