from __future__ import annotations

import os
import subprocess
from pathlib import Path

from repo_merger.fragments import ingest_fragments
from repo_merger.inspection import inspect_fragments
from repo_merger.workspace import mirror_golden_repo, prepare_workspace
from repo_merger.unhandled import UnhandledScenarioRegistry
import shutil


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


def prepare_workspace_with_golden(tmp_path: Path) -> tuple[Path, Path]:
    golden = setup_golden_repo(tmp_path)
    workspace = prepare_workspace(tmp_path / "workspace", "demo", dry_run=False, force=True)
    mirror_golden_repo(golden, workspace.golden, dry_run=False)
    return golden, workspace


def test_git_fragment_in_sync(tmp_path: Path) -> None:
    golden, workspace = prepare_workspace_with_golden(tmp_path)

    fragment_repo = tmp_path / "fragment-sync"
    run_git(["clone", str(golden), str(fragment_repo)], cwd=tmp_path)

    records = ingest_fragments([fragment_repo], workspace, dry_run=False)
    analyses = inspect_fragments(records, workspace, dry_run=False)

    assert analyses[0].status == "in-sync"
    assert (workspace.root / "analysis.json").exists()
    assert analyses[0].handlers == []


def test_git_fragment_diverged(tmp_path: Path) -> None:
    golden, workspace = prepare_workspace_with_golden(tmp_path)
    fragment_repo = tmp_path / "fragment-diverged"
    run_git(["clone", str(golden), str(fragment_repo)], cwd=tmp_path)
    (fragment_repo / "app.txt").write_text("two\n")
    run_git(["add", "app.txt"], fragment_repo)
    run_git(["commit", "-m", "change"], fragment_repo)

    records = ingest_fragments([fragment_repo], workspace, dry_run=False)
    analyses = inspect_fragments(records, workspace, dry_run=False)

    assert analyses[0].status == "diverged"
    assert analyses[0].diff_summary is not None


def test_non_git_fragment_manifest(tmp_path: Path) -> None:
    _, workspace = prepare_workspace_with_golden(tmp_path)
    fragment_dir = tmp_path / "non-git-fragment"
    fragment_dir.mkdir()
    (fragment_dir / "data.txt").write_text("hello\n")

    records = ingest_fragments([fragment_dir], workspace, dry_run=False)
    analyses = inspect_fragments(records, workspace, dry_run=False)

    assert analyses[0].status in {"matched", "non-git"}
    assert analyses[0].manifest_path is not None
    assert Path(analyses[0].manifest_path).exists()


def test_handler_flag_for_missing_git(tmp_path: Path) -> None:
    golden, workspace = prepare_workspace_with_golden(tmp_path)
    fragment_repo = tmp_path / "fragment-missing-git"
    run_git(["clone", str(golden), str(fragment_repo)], cwd=tmp_path)

    records = ingest_fragments([fragment_repo], workspace, dry_run=False)
    fragment_copy = Path(records[0].destination)
    shutil.rmtree(fragment_copy / ".git")

    registry_root = tmp_path / "handler-root"
    registry = UnhandledScenarioRegistry(repo_root=registry_root)

    analyses = inspect_fragments(records, workspace, dry_run=False, registry=registry)

    assert analyses[0].handlers
    assert (registry_root / "HANDLERS.md").exists()
