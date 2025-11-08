from __future__ import annotations

import subprocess
from pathlib import Path


def is_bare_repo(path: Path) -> bool:
    path = path.expanduser().resolve()
    head = path / "HEAD"
    objects = path / "objects"
    refs = path / "refs"
    git_dir = path / ".git"
    return head.is_file() and objects.is_dir() and refs.is_dir() and not git_dir.exists()


def has_git_dir(path: Path) -> bool:
    return (path / ".git").is_dir()


def read_git_config(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def has_remote_from_config(config_text: str) -> bool:
    lowered = config_text.lower()
    return "remote \"" in lowered or "url =" in lowered


def clone_repo(source: Path, destination: Path) -> None:
    subprocess.run(
        ["git", "clone", str(source), str(destination)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
