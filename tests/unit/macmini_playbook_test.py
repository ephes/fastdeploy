import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PLAYBOOK = Path(__file__).resolve().parents[2] / "ansible" / "deploy-macmini.yml"
RUNTIME_TASKS = ("Sync fastDeploy source code to macmini", "Create .env file")
VALIDATION_TASK = "Sync services from filesystem to database"
UNIT_TASK = "Create systemd service for FastDeploy"
RESTART = "restart fastdeploy"


@pytest.fixture
def macmini_play() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text())[0]


@pytest.mark.parametrize(
    ("changed_tasks", "valid", "expected_restarts"),
    [
        ((RUNTIME_TASKS[0],), True, 1),
        ((RUNTIME_TASKS[1],), True, 1),
        (RUNTIME_TASKS, True, 1),
        ((), True, 0),
        (RUNTIME_TASKS, False, 0),
    ],
    ids=["source-only", "env-only", "both", "unchanged", "validation-fails"],
)
def test_macmini_restart_follows_changed_runtime_inputs(
    macmini_play: dict, tmp_path: Path, changed_tasks: tuple[str, ...], valid: bool, expected_restarts: int
) -> None:
    # Preserve task order and notification wiring while replacing all host actions.
    tasks = []
    for task in macmini_play["tasks"]:
        name = task["name"]
        if name in (*RUNTIME_TASKS, UNIT_TASK):
            tasks.append(
                {
                    "name": name,
                    "ansible.builtin.debug": {"msg": "mock converge"},
                    "changed_when": name in changed_tasks,
                    **({"notify": task["notify"]} if "notify" in task else {}),
                }
            )
        elif name == VALIDATION_TASK:
            tasks.append({"name": name, "ansible.builtin.assert": {"that": [valid]}})
        elif task.get("meta") == "flush_handlers":
            tasks.append(task)

    handlers = [
        {"name": handler["name"], "ansible.builtin.debug": {"msg": "mock handler"}}
        for handler in macmini_play["handlers"]
    ]
    playbook = tmp_path / "converge.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "force_handlers": macmini_play.get("force_handlers", False),
                    "tasks": tasks,
                    "handlers": handlers,
                }
            ]
        )
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\n")
    result = subprocess.run(
        [sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", str(playbook)],
        capture_output=True,
        text=True,
        env={**os.environ, "ANSIBLE_CONFIG": str(config), "ANSIBLE_HOME": str(tmp_path / ".ansible")},
        timeout=30,
        check=False,
    )
    assert result.returncode == (0 if valid else 2), result.stdout + result.stderr
    assert result.stdout.count(f"RUNNING HANDLER [{RESTART}]") == expected_restarts, result.stdout


def test_macmini_source_sync_excludes_local_vault_password(macmini_play: dict, tmp_path: Path) -> None:
    rsync = shutil.which("rsync")
    if rsync is None:
        pytest.skip("rsync is required to exercise the Mac mini source filters")

    sync, _ = RUNTIME_TASKS
    sync_task = next(task for task in macmini_play["tasks"] if task["name"] == sync)
    options = sync_task["ansible.posix.synchronize"]["rsync_opts"]
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "ansible").mkdir(parents=True)
    (target / "ansible").mkdir(parents=True)
    (source / ".vault_password").write_text("local sentinel")
    (source / "ansible" / ".vault_password").write_text("local sentinel")
    (source / "ansible" / "deploy.yml").write_text("managed source")
    managed_password = target / "ansible" / ".vault_password"
    managed_password.write_text("managed sentinel")

    subprocess.run(
        [rsync, "-a", *options, f"{source}/", f"{target}/"],
        capture_output=True,
        timeout=15,
        check=True,
    )

    assert not (target / ".vault_password").exists()
    assert managed_password.read_text() == "managed sentinel"
    assert (target / "ansible" / "deploy.yml").read_text() == "managed source"
    render_task = next(task for task in macmini_play["tasks"] if task["name"] == "Create .vault_password file")
    assert render_task["template"]["mode"] == "0600"
