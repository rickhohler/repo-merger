from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from .fragments import FragmentRecord
from .workspace import RepoMergerError, WorkspacePaths


@dataclass
class RecoveryResult:
    fragment_id: str
    recovered_path: str
    status: str
    message: str = ""


def recover_fragments(
    records: Sequence[FragmentRecord],
    workspace: WorkspacePaths,
    *,
    dry_run: bool = False,
    threshold_minutes: int = 30,
) -> List[RecoveryResult]:
    del threshold_minutes  # placeholder for future heuristic grouping
    recovered_root = workspace.root / "recovered"
    results: List[RecoveryResult] = []
    for record in records:
        fragment_path = Path(record.destination)
        if fragment_path.is_dir() and (fragment_path / ".git").exists():
            continue
        if fragment_path.is_file():
            continue  # skip stray files for now
        result = _recover_fragment(record, fragment_path, recovered_root, dry_run=dry_run)
        results.append(result)
    return results


def _recover_fragment(
    record: FragmentRecord,
    fragment_path: Path,
    recovered_root: Path,
    *,
    dry_run: bool,
) -> RecoveryResult:
    target = recovered_root / record.fragment_id
    if dry_run:
        logging.info("Dry run: would recover fragment %s into %s", fragment_path, target)
        return RecoveryResult(
            fragment_id=record.fragment_id,
            recovered_path=str(target),
            status="dry-run",
        )

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree(fragment_path, target)
    _initialize_git_repo(target)
    record.recovered_repo = str(target)
    logging.info("Recovered fragment %s into %s", record.fragment_id, target)
    return RecoveryResult(
        fragment_id=record.fragment_id,
        recovered_path=str(target),
        status="recovered",
    )


def _copy_tree(source: Path, destination: Path) -> None:
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if ".git" in relative.parts:
            continue
        dest_path = destination / relative
        if item.is_dir():
            dest_path.mkdir(parents=True, exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest_path)


def _initialize_git_repo(path: Path) -> None:
    _run_git(["init"], cwd=path)
    _run_git(["add", "."], cwd=path)
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "repo-merger")
    env.setdefault("GIT_AUTHOR_EMAIL", "repo-merger@example.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    _run_git(["commit", "-m", "Recovered snapshot"], cwd=path, env=env)


def _run_git(args: Sequence[str], *, cwd: Path, env: dict | None = None) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RepoMergerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
