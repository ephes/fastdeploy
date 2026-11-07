"""Audit the frozen, complete Python graph for this interpreter; fail closed."""

import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="fastdeploy-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--frozen",
                "--all-groups",
                "--all-extras",
                "--no-hashes",
                "--no-emit-project",
                "--quiet",
                "--output-file",
                str(requirements),
            ],
            check=True,
        )
        subprocess.run(
            [
                "uvx",
                "--python",
                sys.executable,
                "pip-audit==2.10.1",
                "--cache-dir",
                str(Path(directory) / "cache"),
                "--disable-pip",
                "--no-deps",
                "-r",
                str(requirements),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
