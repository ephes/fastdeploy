"""
The deploy task owns the lifetime of the deploy script it starts.

These tests run small synthetic child processes (never sudo, never a real
deploy script) through ``DeployTask.deploy_steps`` and check that no child
or descendant survives when reading its output stops early.
"""

import asyncio
import contextlib
import os
import sys
import textwrap
import time
from unittest.mock import patch

import pytest

from deploy import tasks
from deploy.tasks import DeploymentContext, DeployTask

pytestmark = pytest.mark.asyncio

real_create_subprocess_exec = asyncio.create_subprocess_exec


class RecordingClient:
    def __init__(self):
        self.posted = []

    async def post(self, url, json=None):
        self.posted.append(json)

        class Response:
            def raise_for_status(self):
                pass

        return Response()


@pytest.fixture
def task():
    task = DeployTask(
        deploy_script="/never-executed/deploy.sh",
        access_token="token",
        steps_url="http://test/steps",
        deployment_finish_url="http://test/finish",
        context=DeploymentContext(),
        path_for_deploy=os.environ.get("PATH", "/usr/bin:/bin"),
        attempts=1,
        client=RecordingClient(),
    )
    return task


@pytest.fixture
def run_child(tmp_path, monkeypatch):
    """
    Make deploy_steps run the given Python source instead of "sudo ... deploy
    script", passing everything else (pipes, limit, process group) through.
    Returns the kwargs deploy_steps used and the cleaned up config paths.
    """
    seen = {"kwargs": None, "cleanups": []}

    def install(source: str):
        script = tmp_path / "child.py"
        script.write_text(textwrap.dedent(source))

        async def create(*command, **kwargs):
            seen["kwargs"] = kwargs
            return await real_create_subprocess_exec(sys.executable, str(script), str(tmp_path), **kwargs)

        monkeypatch.setattr(tasks.asyncio, "create_subprocess_exec", create)
        original_cleanup = tasks.SecureConfig.cleanup_config

        def cleanup(config_path):
            seen["cleanups"].append(config_path)
            return original_cleanup(config_path)

        monkeypatch.setattr(tasks.SecureConfig, "cleanup_config", staticmethod(cleanup))
        return seen

    return install


# Child: starts a descendant, records both pids, prints a marker line and waits.
WAITING_CHILD = """
    import os, subprocess, sys, time
    out = sys.argv[1]
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    with open(os.path.join(out, "pids.tmp"), "w") as f:
        f.write(f"{os.getpid()} {grandchild.pid}")
    os.rename(os.path.join(out, "pids.tmp"), os.path.join(out, "pids"))
    %s
    time.sleep(300)
"""


def read_pids(tmp_path, timeout=10.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (tmp_path / "pids").exists():
            return [int(pid) for pid in (tmp_path / "pids").read_text().split()]
        time.sleep(0.02)
    raise AssertionError("child did not start")


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A killed orphan can linger as a zombie for a moment until init reaps it.
    try:
        import psutil
    except ImportError:  # pragma: no cover
        return True
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def assert_all_gone(pids, timeout=10.0):
    deadline = time.monotonic() + timeout
    alive = pids
    while time.monotonic() < deadline:
        alive = [pid for pid in pids if is_alive(pid)]
        if not alive:
            return
        time.sleep(0.05)
    for pid in alive:  # do not leak synthetic children from a failing test
        with contextlib.suppress(OSError):
            os.kill(pid, 9)
    raise AssertionError(f"processes still alive: {alive}")


async def wait_for_pids(tmp_path):
    return await asyncio.to_thread(read_pids, tmp_path)


async def test_invalid_utf8_output_does_not_abandon_the_script(task, run_child):
    seen = run_child(
        """
        import json, sys
        sys.stdout.buffer.write(b"\\xff\\xfe not utf-8\\n")
        sys.stdout.buffer.write(b'{"name": "broken \\xff", "state": "success"}\\n')
        print(json.dumps({"name": "after", "state": "success"}), flush=True)
        """
    )

    await task.deploy_steps()

    assert [step["name"] for step in task.client.posted] == ["broken �", "after"]
    assert seen["kwargs"]["start_new_session"] is True
    assert len(seen["cleanups"]) == 1


async def test_over_limit_line_is_skipped_and_the_script_is_reaped(task, run_child, monkeypatch, capsys):
    monkeypatch.setattr(tasks, "MAX_ASYNCIO_STDOUT_SIZE", 1024)
    seen = run_child(
        """
        import json, sys
        print("x" * 100_000, flush=True)
        print(json.dumps({"name": "after", "state": "success"}), flush=True)
        sys.exit(3)
        """
    )

    with pytest.raises(RuntimeError, match="exited with code 3"):
        await task.deploy_steps()

    assert [step["name"] for step in task.client.posted] == ["after"]
    assert capsys.readouterr().err.count("skipped a deploy output line") == 1
    assert len(seen["cleanups"]) == 1


async def test_the_end_of_an_over_limit_line_is_not_taken_for_a_step(task, run_child, monkeypatch):
    """
    The line arrives in pieces: an over-limit prefix first, and later a suffix
    that on its own would be a valid step result. All of it is one line.
    """
    monkeypatch.setattr(tasks, "MAX_ASYNCIO_STDOUT_SIZE", 1024)
    run_child(
        """
        import json, sys, time
        out = sys.stdout
        out.write("x" * 5000)
        out.flush()
        time.sleep(0.5)  # the reader hits the limit before the newline exists
        out.write("\\r" + json.dumps({"name": "smuggled", "state": "success"}) + "\\n")
        out.flush()
        # an over-limit line which reaches the reader together with its newline
        out.write("y" * 3000 + "\\n" + json.dumps({"name": "after", "state": "success"}) + "\\n")
        out.flush()
        out.write(json.dumps({"name": "last without newline", "state": "success"}))
        out.flush()
        """
    )

    await task.deploy_steps()

    assert [step["name"] for step in task.client.posted] == ["after", "last without newline"]


async def test_an_over_limit_line_without_end_does_not_hang(task, run_child, monkeypatch):
    monkeypatch.setattr(tasks, "MAX_ASYNCIO_STDOUT_SIZE", 1024)
    run_child(
        """
        import sys
        sys.stdout.write("x" * 5000)
        """
    )

    await asyncio.wait_for(task.deploy_steps(), timeout=10)

    assert task.client.posted == []


async def test_cancellation_stops_child_and_descendants(task, run_child, tmp_path):
    seen = run_child(WAITING_CHILD % 'print("started", flush=True)')

    running = asyncio.create_task(task.deploy_steps())
    pids = await wait_for_pids(tmp_path)
    assert all(is_alive(pid) for pid in pids)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert_all_gone(pids)
    assert len(seen["cleanups"]) == 1


async def test_read_error_stops_child_and_descendants(task, run_child, tmp_path):
    seen = run_child(WAITING_CHILD % 'print("started", flush=True)')

    async def create_with_failing_reader(*command, **kwargs):
        proc = await create(*command, **kwargs)
        original_readuntil = proc.stdout.readuntil

        async def readuntil(separator=b"\n"):
            await original_readuntil(separator)
            await wait_for_pids(tmp_path)
            raise OSError("pipe broke")

        proc.stdout.readuntil = readuntil
        return proc

    create = tasks.asyncio.create_subprocess_exec
    with (
        patch.object(tasks.asyncio, "create_subprocess_exec", create_with_failing_reader),
        pytest.raises(OSError, match="pipe broke"),
    ):
        await task.deploy_steps()

    assert_all_gone(read_pids(tmp_path))
    assert len(seen["cleanups"]) == 1


async def test_child_ignoring_sigterm_is_killed(task, run_child, tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "DEPLOY_STOP_TIMEOUT", 0.3)
    run_child(
        WAITING_CHILD % 'import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("started", flush=True)'
    )

    running = asyncio.create_task(task.deploy_steps())
    pids = await wait_for_pids(tmp_path)
    await asyncio.sleep(0.2)  # let the child install its SIGTERM handler
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert_all_gone(pids)


async def test_descendant_outliving_the_script_is_killed(task, run_child, tmp_path, monkeypatch):
    """
    The script itself exits on SIGTERM, but its descendant ignores SIGTERM and
    holds no pipe of the task. The group is only gone after SIGKILL.
    """
    monkeypatch.setattr(tasks, "DEPLOY_STOP_TIMEOUT", 0.5)
    run_child(
        """
        import os, subprocess, sys, time
        out = sys.argv[1]
        stubborn = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)"
        grandchild = subprocess.Popen(
            [sys.executable, "-c", stubborn],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)  # let it install its handler
        with open(os.path.join(out, "pids.tmp"), "w") as f:
            f.write(f"{os.getpid()} {grandchild.pid}")
        os.rename(os.path.join(out, "pids.tmp"), os.path.join(out, "pids"))
        print("started", flush=True)
        time.sleep(300)
        """
    )

    running = asyncio.create_task(task.deploy_steps())
    pids = await wait_for_pids(tmp_path)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    # no grace period here: the cleanup itself has to have finished the group
    assert [pid for pid in pids if is_alive(pid)] == []


async def test_run_deploy_reports_failure_after_stopping_the_child(task, run_child, tmp_path):
    """The record is only finished as failed once the script is really gone."""
    run_child(WAITING_CHILD % 'print("started", flush=True)')
    finished = []

    async def finish_deployment(self):
        finished.append([is_alive(pid) for pid in read_pids(tmp_path)])

    with patch.object(DeployTask, "finish_deployment", finish_deployment):
        running = asyncio.create_task(task.run_deploy())
        pids = await wait_for_pids(tmp_path)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    assert_all_gone(pids)
    assert [step["name"] for step in task.client.posted] == ["failed step"]
    assert finished == [[False, False]]


async def test_normal_exit_does_not_signal_the_process_group(task, run_child):
    run_child(
        """
        import json
        print(json.dumps({"name": "only", "state": "success"}), flush=True)
        """
    )

    with patch.object(tasks.os, "killpg") as killpg:
        await task.deploy_steps()

    killpg.assert_not_called()
    assert [step["name"] for step in task.client.posted] == ["only"]


# --- the deploy command is an argument list, not a shell command line ---


@pytest.fixture
def fake_sudo(tmp_path):
    """A directory to put on PATH whose "sudo -u USER CMD ARGS" just runs CMD ARGS and records its arguments."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sudo = bin_dir / "sudo"
    sudo.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, os, sys
            with open({str(tmp_path / "sudo_args.json")!r}, "w") as f:
                json.dump(sys.argv[1:], f)
            assert sys.argv[1] == "-u"
            os.execv(sys.argv[3], sys.argv[3:])
            """
        )
    )
    sudo.chmod(0o755)
    return bin_dir


def write_deploy_script(path, tmp_path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, sys
            with open({str(tmp_path / "script_args.json")!r}, "w") as f:
                json.dump(sys.argv[1:], f)
            print(json.dumps({{"name": "ran", "state": "success"}}), flush=True)
            """
        )
    )
    path.chmod(0o755)


async def run_deploy_steps_with(task, fake_sudo, deploy_script, monkeypatch, sudo_user="deploy"):
    monkeypatch.setattr(tasks.settings, "sudo_user", sudo_user)
    task.deploy_script = deploy_script
    task.path_for_deploy = f"{fake_sudo}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    # sudo itself is looked up on the PATH of the deploy task
    monkeypatch.setenv("PATH", task.path_for_deploy)
    await asyncio.wait_for(task.deploy_steps(), timeout=30)


async def test_deploy_command_runs_the_script_with_the_config_argument(task, fake_sudo, tmp_path, monkeypatch):
    """The invocation existing services rely on: sudo -u USER SCRIPT --config PATH."""
    import json

    script = tmp_path / "services" / "dummy" / "deploy.sh"
    write_deploy_script(script, tmp_path)

    await run_deploy_steps_with(task, fake_sudo, str(script), monkeypatch)

    sudo_args = json.loads((tmp_path / "sudo_args.json").read_text())
    assert sudo_args[:3] == ["-u", "deploy", str(script)]
    assert sudo_args[3] == "--config"
    assert len(sudo_args) == 5
    assert json.loads((tmp_path / "script_args.json").read_text()) == sudo_args[3:]
    assert [step["name"] for step in task.client.posted] == ["ran"]


async def test_relative_deploy_script_is_resolved_below_the_services_root(task, fake_sudo, tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(tasks.settings, "services_dir_name", "services")
    monkeypatch.setattr(tasks.settings, "project_root", tmp_path)
    write_deploy_script(tmp_path / "services" / "dummy" / "deploy.sh", tmp_path)

    await run_deploy_steps_with(task, fake_sudo, "dummy/deploy.sh", monkeypatch)

    sudo_args = json.loads((tmp_path / "sudo_args.json").read_text())
    assert sudo_args[2] == str(tmp_path / "services" / "dummy" / "deploy.sh")
    assert [step["name"] for step in task.client.posted] == ["ran"]


async def test_shell_syntax_in_the_deploy_script_is_not_interpreted(task, fake_sudo, tmp_path, monkeypatch):
    """A script path with shell metacharacters is one argument: nothing else runs."""
    injected = tmp_path / "injected"
    script = tmp_path / "services" / f"deploy.sh; touch {injected} #"
    write_deploy_script(script, tmp_path)

    await run_deploy_steps_with(task, fake_sudo, str(script), monkeypatch)

    assert not injected.exists()
    assert [step["name"] for step in task.client.posted] == ["ran"]


async def test_shell_syntax_in_the_sudo_user_is_not_interpreted(task, fake_sudo, tmp_path, monkeypatch):
    import json

    injected = tmp_path / "injected"
    script = tmp_path / "services" / "deploy.sh"
    write_deploy_script(script, tmp_path)
    sudo_user = f"deploy true; touch {injected};"

    await run_deploy_steps_with(task, fake_sudo, str(script), monkeypatch, sudo_user=sudo_user)

    assert not injected.exists()
    assert json.loads((tmp_path / "sudo_args.json").read_text())[:3] == ["-u", sudo_user, str(script)]
