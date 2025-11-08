from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Sequence


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


def clone_repo(source: Path, destination: Path, *, bare: bool = False, mirror: bool = False) -> None:
    args = ["git", "clone"]
    if bare:
        args.append("--bare")
    if mirror:
        args.append("--mirror")
    args.extend([str(source), str(destination)])
    subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_gh_command(args: Sequence[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout
