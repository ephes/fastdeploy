import contextlib
import os

from pathlib import Path


@contextlib.contextmanager
def working_directory(path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev_cwd)


def get_directories(path: Path) -> list[str]:
    """Returns a list of directories in a given path."""
    for entry_path in path.iterdir():
        if entry_path.is_dir():
            yield entry_path.name
