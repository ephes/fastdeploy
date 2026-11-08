"""Launcher cleanup uses only the owned process group; synthetic process model."""

import contextlib
import signal
import subprocess
from unittest.mock import Mock

import pytest

from deploy import tasks


@pytest.mark.parametrize("needs_kill", [False, True])
def test_supervisor_start_failure_stops_group_reaps_and_cleans_config(tmp_path, monkeypatch, needs_kill):
    # A process model keeps assertions independent of OS process inspection.
    members = {73001, 73002}  # owned child and descendant
    signals, waits = [], []
    process = Mock(pid=73001)

    def wait(timeout=None):
        waits.append(timeout)
        if members:
            raise subprocess.TimeoutExpired("synthetic child", timeout)
        return 0

    process.wait.side_effect = wait

    def killpg(pgid, sig):
        assert pgid == process.pid
        if not members:
            raise ProcessLookupError
        if sig:
            signals.append(sig)
        if sig == signal.SIGKILL or (sig == signal.SIGTERM and not needs_kill):
            members.clear()

    monkeypatch.setattr(tasks.os, "killpg", killpg)
    monkeypatch.setattr(tasks.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(tasks, "LAUNCH_STOP_TIMEOUT_SECONDS", 0.001)
    error = RuntimeError("synthetic supervisor failure")
    monkeypatch.setattr(tasks.threading.Thread, "start", Mock(side_effect=error))
    with pytest.raises(RuntimeError) as caught:
        tasks.run_deploy({"DEPLOYMENT_ID": "synthetic", "ACCESS_TOKEN": "token-sentinel"})
    assert caught.value is error or caught.value.__cause__ is error
    assert not members
    assert waits and all(timeout is not None for timeout in waits)
    assert signals == ([signal.SIGTERM, signal.SIGKILL] if needs_kill else [signal.SIGTERM])
    assert not list(tmp_path.glob("deploy_*.json"))


def test_supervisor_failure_stops_synthetic_child_and_descendant(tmp_path, monkeypatch):
    import os
    import sys
    import time

    # Both processes write completion markers on TERM. No /proc, shell tools,
    # host services, real deployment commands or OS-specific PID inspection.
    descendant = """import pathlib, signal, sys, time
root = pathlib.Path(sys.argv[1])
def stop(*args):
    (root / "descendant-stopped").touch()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
(root / "descendant-ready").touch()
time.sleep(60)
"""
    source = """import pathlib, signal, subprocess, sys, time
root = pathlib.Path(sys.argv[1])
child = subprocess.Popen([sys.executable, "-c", sys.argv[2], str(root)])
def stop(*args):
    child.wait(timeout=5)
    (root / "parent-stopped").touch()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
while not (root / "descendant-ready").exists():
    time.sleep(.01)
(root / "parent-ready").touch()
time.sleep(60)
"""
    real_popen = subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = real_popen([sys.executable, "-c", source, str(tmp_path), descendant], **kwargs)
        children.append(child)
        deadline = time.monotonic() + 10
        while not (tmp_path / "parent-ready").exists():
            assert time.monotonic() < deadline, "synthetic child did not initialize"
            time.sleep(0.01)
        return child

    monkeypatch.setattr(tasks.subprocess, "Popen", spawn)
    monkeypatch.setattr(tasks.threading.Thread, "start", Mock(side_effect=RuntimeError("supervisor unavailable")))
    monkeypatch.setattr(tasks, "LAUNCH_STOP_TIMEOUT_SECONDS", 1)
    try:
        with pytest.raises(RuntimeError):
            tasks.run_deploy({"DEPLOYMENT_ID": "synthetic"})
        assert children[0].poll() is not None
        assert (tmp_path / "descendant-stopped").exists()
        assert (tmp_path / "parent-stopped").exists()
        assert not list(tmp_path.glob("deploy_*.json"))
    finally:
        for child in children:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def test_launcher_cleanup_total_blocking_budget_is_short(monkeypatch):
    elapsed = 0.0

    def advance(seconds):
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(tasks.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(tasks.time, "sleep", advance)
    monkeypatch.setattr(tasks.os, "killpg", Mock())  # group does not acknowledge exit
    child = Mock(pid=73001)

    def stuck_wait(timeout):
        advance(timeout)
        raise subprocess.TimeoutExpired("synthetic", timeout)

    child.wait.side_effect = stuck_wait
    tasks.stop_launch_process(child)
    assert elapsed <= 0.301  # TERM, KILL and reap together, with a synthetic clock
