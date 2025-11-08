from __future__ import annotations

import subprocess
from pathlib import Path
import json
from typing import List, Sequence, Union


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


def run_git(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def git_rev_parse(repo: Path) -> str:
    result = run_git(repo, ["rev-parse", "HEAD"])
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse failed for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def git_has_commit(repo: Path, commit: str) -> bool:
    result = run_git(repo, ["cat-file", "-e", f"{commit}^{{commit}}"])
    return result.returncode == 0


def git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = run_git(repo, ["merge-base", "--is-ancestor", ancestor, descendant])
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(f"git merge-base failed for {repo}: {result.stderr.strip()}")


def clone_repo(
    source: Union[Path, str],
    destination: Path,
    *,
    bare: bool = False,
    mirror: bool = False,
) -> None:
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


def list_user_repos(limit: int | None = None, *, visibility: str | None = None) -> List[dict]:
    cmd = [
        "repo",
        "list",
        "--json",
        "nameWithOwner,name,sshUrl,cloneUrl,isPrivate",
    ]
    if limit:
        cmd += ["--limit", str(limit)]
    if visibility:
        cmd += ["--visibility", visibility]
    output = run_gh_command(cmd)
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse gh repo list output") from exc
    return data
