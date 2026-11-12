"""Synthetic process failures must never turn into a successful empty audit."""

import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_audit_exports_complete_frozen_graph_before_pinned_audit(monkeypatch):
    calls = []

    def run(command, *, check):
        assert check is True
        calls.append(command)
        if command[0] == "uv":
            Path(command[-1]).write_text("synthetic-package==1.0\n")
        else:
            assert Path(command[-1]).read_text() == "synthetic-package==1.0\n"

    monkeypatch.setattr(subprocess, "run", run)
    runpy.run_path(str(ROOT / "scripts/audit_python.py"))["main"]()
    assert {"--frozen", "--all-groups", "--all-extras", "--no-emit-project"} <= set(calls[0])
    assert "pip-audit==2.10.1" in calls[1]
    assert "--disable-pip" in calls[1] and "--no-deps" in calls[1]
    assert not Path(calls[0][-1]).exists()


@pytest.mark.parametrize("failed_command", ["uv", "uvx"])
def test_failed_export_or_audit_fails_closed_and_cleans_up(monkeypatch, failed_command):
    calls = []

    def run(command, *, check):
        assert check is True
        calls.append(command)
        if command[0] == failed_command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        runpy.run_path(str(ROOT / "scripts/audit_python.py"))["main"]()
    assert [command[0] for command in calls] == (["uv"] if failed_command == "uv" else ["uv", "uvx"])
    assert not Path(calls[0][-1]).exists()


def test_ci_runs_independent_complete_audits_on_push_and_schedule():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 treats on as boolean.
    assert "push" in triggers and triggers["schedule"]
    assert workflow["permissions"] == {"contents": "read"}
    python = workflow["jobs"]["audit-python"]
    npm = workflow["jobs"]["audit-npm"]
    assert set(python["strategy"]["matrix"]["python-version"]) == {"3.11", "3.14"}
    for job in (python, npm):
        assert "needs" not in job
        assert not job.get("continue-on-error", False)
        assert all(not step.get("continue-on-error", False) for step in job["steps"])
    assert any(step.get("run") == "python scripts/audit_python.py" for step in python["steps"])
    assert any(step.get("run") == "npm audit --package-lock-only" for step in npm["steps"])
