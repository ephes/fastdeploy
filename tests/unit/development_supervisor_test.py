"""Verify shutdown through the existing supervisor with two synthetic checkouts."""

import os
import shlex
import signal
import subprocess
import sys
import time
from contextlib import ExitStack

SERVICE = """import atexit, signal, threading
from pathlib import Path
atexit.register(lambda: Path("stopped").touch())
signal.signal(signal.SIGTERM, lambda *_: exit(0))
Path("ready").touch()
threading.Event().wait()
"""


def wait_until(predicate):
    deadline = time.monotonic() + 15
    while not predicate():
        assert time.monotonic() < deadline, "synthetic supervisor did not reach expected state"
        time.sleep(0.02)


def stop_supervisor(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=15)


def test_honcho_shutdown_leaves_other_checkout_running(tmp_path):
    with ExitStack() as resources:
        checkouts = []
        for name in ("selected", "unrelated"):
            root = tmp_path / name
            root.mkdir()
            (root / "service.py").write_text(SERVICE)
            (root / "Procfile").write_text(f"vue: {shlex.quote(sys.executable)} service.py\n")
            log = resources.enter_context((root / "supervisor.log").open("w"))
            process = subprocess.Popen(
                [sys.executable, "-m", "honcho", "start"],
                cwd=root,
                env={"PATH": os.environ["PATH"]},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            resources.callback(stop_supervisor, process)
            checkouts.append((root, process))
        for root, _ in checkouts:
            wait_until((root / "ready").exists)
        selected, supervisor = checkouts[0]
        other, other_supervisor = checkouts[1]
        # Same signal as Ctrl+C to the selected foreground Honcho.
        supervisor.send_signal(signal.SIGINT)
        supervisor.wait(timeout=15)
        assert (selected / "stopped").exists()
        assert other_supervisor.poll() is None
        assert not (other / "stopped").exists()
    assert (other / "stopped").exists()
