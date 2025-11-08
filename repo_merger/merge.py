from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Sequence

from .fragments import FragmentRecord
from .workspace import RepoMergerError, WorkspacePaths


@dataclass
class MergeResult:
    fragment_id: str
    worktree: str
    status: str
    message: str = ""


def merge_fragments(
    records: Sequence[FragmentRecord],
    workspace: WorkspacePaths,
    *,
    dry_run: bool = False,
    resume_from: str | None = None,
) -> List[MergeResult]:
    worktrees_root = workspace.root / "worktrees"
    if not dry_run:
        worktrees_root.mkdir(parents=True, exist_ok=True)
    results: List[MergeResult] = []
    resume_mode = bool(resume_from)

    for record in records:
        if resume_mode and record.fragment_id != resume_from and not results:
            logging.info("Skipping %s until resume target is found", record.fragment_id)
            continue
        resume_mode = False
        result = _merge_single(
            record=record,
            workspace=workspace,
            worktrees_root=worktrees_root,
            dry_run=dry_run,
        )
        results.append(result)

    if not dry_run:
        _write_merge_report(workspace.root / "merge_report.json", results)
    else:
        logging.info("Dry run: merge report not written.")
    return results


def _merge_single(
    record: FragmentRecord,
    workspace: WorkspacePaths,
    worktrees_root: Path,
    *,
    dry_run: bool,
) -> MergeResult:
    fragment_path = Path(record.destination)
    source_repo = fragment_path if (fragment_path / ".git").exists() else None
    if not source_repo and record.recovered_repo:
        source_repo = Path(record.recovered_repo)
    if source_repo is None:
        return MergeResult(
            fragment_id=record.fragment_id,
            worktree="n/a",
            status="skipped",
            message="Fragment has no git metadata or recovered repo.",
        )

    worktree_path = worktrees_root / record.fragment_id
    if dry_run:
        logging.info(
            "Dry run: would create worktree %s for fragment %s", worktree_path, record.fragment_id
        )
        return MergeResult(
            fragment_id=record.fragment_id,
            worktree=str(worktree_path),
            status="dry-run",
        )

    _prepare_worktree(workspace.golden, worktree_path)
    _overlay_fragment(source_repo, worktree_path)
    status_output = _git_status(worktree_path)
    message = status_output.strip() or "No changes detected."
    return MergeResult(
        fragment_id=record.fragment_id,
        worktree=str(worktree_path),
        status="applied" if status_output.strip() else "clean",
        message=message,
    )


def _prepare_worktree(golden_path: Path, worktree_path: Path) -> None:
    if worktree_path.exists():
        shutil.rmtree(worktree_path)
    result = subprocess.run(
        ["git", "-C", str(golden_path), "worktree", "add", "-f", str(worktree_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RepoMergerError(f"git worktree add failed: {result.stderr.strip()}")


def _overlay_fragment(fragment_repo: Path, worktree_path: Path) -> None:
    source_root = fragment_repo
    if (fragment_repo / ".git").is_dir():
        source_root = fragment_repo
    for item in source_root.rglob("*"):
        relative = item.relative_to(source_root)
        if ".git" in relative.parts:
            continue
        target = worktree_path / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _git_status(worktree_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "status", "--short"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RepoMergerError(f"git status failed: {result.stderr.strip()}")
    return result.stdout


def _write_merge_report(report_path: Path, results: Sequence[MergeResult]) -> None:
    payload = {"merges": [asdict(result) for result in results]}
    report_path.write_text(json.dumps(payload, indent=2))
    logging.info("Wrote merge report to %s", report_path)
