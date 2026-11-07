"""Execute real just recipes with synthetic command-line collaborators."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# No PostgreSQL, package installs, process signals or network in these fixtures.
TOOL = """#!{python}
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path(os.environ["FAKE_ROOT"])
with (root / "calls").open("a") as f:
    f.write(json.dumps([name, *args]) + "\\n")
if name == os.environ.get("FAIL_TOOL"):
    print("synthetic permission/connection/SQL failure", file=sys.stderr)
    sys.exit(9)
if name == "psql" and "-c" in args:
    query = args[args.index("-c") + 1]
    if os.environ.get("FAIL_QUERY", "NEVER") in query:
        sys.exit(9)
    if os.environ.get("EXISTS") == "1":
        print("1")
elif name == "psql":
    sys.stdin.read()
elif name == "lsof":
    sys.exit(1)
elif name == "pg_ctl":
    (root / "postgres-running").write_text(str("start" in args))
elif name == "npm":
    (root / "frontend-installed").touch()
elif name == "uv" and args[:1] == ["venv"]:
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/activate").touch()
elif name == "uv" and "secrets" in " ".join(args):
    print("synthetic-local-key")
elif name == "honcho":
    assert (root / "postgres-running").read_text() == "False"
    assert (root / "frontend-installed").exists()
    assert os.environ["SECRET_KEY"]
    assert os.environ["PATH_FOR_DEPLOY"] == os.environ["PATH"]
"""


@pytest.fixture
def recipe_env(tmp_path):
    (tmp_path / "justfile").write_text((ROOT / "justfile").read_text())
    commands = tmp_path / "bin"
    commands.mkdir()
    for name in ("psql", "createdb", "createuser", "pg_dump", "uv", "npm", "initdb", "pg_ctl", "lsof", "honcho"):
        tool = commands / name
        tool.write_text(TOOL.format(python=sys.executable))
        tool.chmod(0o755)
    env = {"PATH": str(commands) + os.pathsep + os.environ["PATH"], "FAKE_ROOT": str(tmp_path)}
    return tmp_path, env


def run_recipe(recipe_env, *args, **updates):
    root, env = recipe_env
    return subprocess.run(
        [shutil.which("just"), *args], cwd=root, env={**env, **updates}, text=True, capture_output=True, timeout=15
    )


def calls(recipe_env):
    return [json.loads(line) for line in (recipe_env[0] / "calls").read_text().splitlines()]


@pytest.mark.parametrize("filename", ["README.md", "docs/cli.md"])
def test_fresh_bootstrap_handoff(recipe_env, filename):
    text = (ROOT / filename).read_text()
    quickstart = text[text.index("## Quick Start") :]
    script = re.search(r"```shell\n(.*?)```", quickstart, re.S).group(1)
    root, env = recipe_env
    result = subprocess.run(["bash", "-ec", script], cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    invoked = calls(recipe_env)
    assert [c[-1] for c in invoked if c[0] == "pg_ctl"] == ["start", "stop"]
    assert invoked.index(["npm", "--prefix", "frontend", "ci"]) < invoked.index(["honcho", "start"])


def test_database_rerun_preserves_existing_resources(recipe_env):
    result = run_recipe(recipe_env, "db-create", EXISTS="1")
    assert result.returncode == 0, result.stderr
    assert all(c[0] == "psql" and "-c" in c for c in calls(recipe_env))


def test_database_creates_missing_resources(recipe_env):
    result = run_recipe(recipe_env, "db-create")
    assert result.returncode == 0, result.stderr
    invoked = calls(recipe_env)
    assert ["createdb", "deploy"] in invoked
    assert ["createuser", "deploy"] in invoked
    assert ["createdb", "deploy_test"] in invoked
    assert ["pg_dump", "--schema-only", "deploy"] in invoked
    assert ["psql", "-X", "-v", "ON_ERROR_STOP=1", "--dbname", "deploy_test"] in invoked


@pytest.mark.parametrize("tool", ["createdb", "createuser", "pg_dump", "psql"])
def test_database_tool_failures_propagate(recipe_env, tool):
    result = run_recipe(recipe_env, "db-create", FAIL_TOOL=tool)
    assert result.returncode != 0
    assert "Databases created" not in result.stdout
    assert any(c[0] == tool for c in calls(recipe_env))


@pytest.mark.parametrize("query", ["pg_database", "pg_roles", "deploy_test"])
def test_database_catalog_failures_propagate(recipe_env, query):
    result = run_recipe(recipe_env, "db-create", FAIL_QUERY=query)
    assert result.returncode != 0
    assert "Databases created" not in result.stdout


def test_database_sql_application_failure_propagates(recipe_env):
    root, _ = recipe_env
    tool = root / "bin/psql"
    tool.write_text(tool.read_text().replace("sys.stdin.read()", "sys.stdin.read(); sys.exit(9)"))
    result = run_recipe(recipe_env, "db-create")
    assert result.returncode != 0
    assert "Databases created" not in result.stdout
