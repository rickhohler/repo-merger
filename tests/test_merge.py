from __future__ import annotations

import os
import subprocess
from pathlib import Path

from repo_merger.fragments import ingest_fragments
from repo_merger.merge import merge_fragments
from repo_merger.workspace import mirror_golden_repo, prepare_workspace


def run_git(args: list[str], cwd: Path) -> None:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "repo-merger")
    env.setdefault("GIT_AUTHOR_EMAIL", "repo-merger@example.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    subprocess.run(["git", *args], cwd=str(cwd), check=True, env=env)


def setup_golden_repo(base: Path) -> Path:
    golden = base / "golden-src"
    golden.mkdir()
    run_git(["init"], golden)
    (golden / "app.txt").write_text("one\n")
    run_git(["add", "."], golden)
    run_git(["commit", "-m", "init"], golden)
    return golden


def test_merge_fragments_applies_changes(tmp_path: Path) -> None:
    golden = setup_golden_repo(tmp_path)
    workspace = prepare_workspace(tmp_path / "workspace", "demo", dry_run=False, force=True)
    mirror_golden_repo(golden, workspace.golden, dry_run=False)

    fragment_repo = tmp_path / "fragment"
    run_git(["clone", str(golden), str(fragment_repo)], cwd=tmp_path)
    (fragment_repo / "app.txt").write_text("two\n")
    run_git(["add", "app.txt"], fragment_repo)
    run_git(["commit", "-m", "fragment change"], fragment_repo)

    records = ingest_fragments([fragment_repo], workspace, dry_run=False)
    results = merge_fragments(records, workspace, dry_run=False)

    assert results
    assert Path(results[0].worktree).exists()
    assert results[0].status in {"applied", "clean"}
