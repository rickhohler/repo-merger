from __future__ import annotations

import logging
from pathlib import Path
import subprocess

import pytest

from repo_merger.workspace import (
    RepoMergerError,
    derive_identifier,
    mirror_golden_repo,
    prepare_workspace,
)


def make_git_config(path: Path, remote_url: str) -> None:
    git_dir = path / ".git"
    (git_dir).mkdir(parents=True, exist_ok=True)
    config = git_dir / "config"
    config.write_text(
        "[core]\n\trepositoryformatversion = 0\n"
        '\tfilemode = true\n'
        '\tbare = false\n'
        '\tlogallrefupdates = true\n'
        "[remote \"origin\"]\n"
        f"\turl = {remote_url}\n"
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
    )


def test_derive_identifier_uses_origin_remote(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    golden.mkdir()
    make_git_config(golden, "git@github.com:rickhohler/repo-merger.git")

    identifier = derive_identifier(golden)

    assert identifier == "rickhohler-repo-merger"


def test_derive_identifier_falls_back_to_directory(tmp_path: Path) -> None:
    golden = tmp_path / "repo-golden"
    golden.mkdir()
    identifier = derive_identifier(golden)
    assert identifier == "repo-golden"


def test_prepare_workspace_creates_structure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    golden_src = tmp_path / "golden-src"
    golden_src.mkdir()
    (golden_src / "README.md").write_text("sample")

    paths = prepare_workspace(workspace, "demo", dry_run=False, force=False)
    assert paths.root.exists()
    assert paths.golden.exists()
    assert paths.fragments.exists()

    mirror_golden_repo(golden_src, paths.golden, dry_run=False)
    copied = paths.golden / "README.md"
    assert copied.read_text() == "sample"


def test_prepare_workspace_respects_force_flag(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    paths_first = prepare_workspace(workspace, "demo", dry_run=False, force=False)
    assert paths_first.root.exists()

    # Re-running without force should reuse the existing structure
    paths_second = prepare_workspace(workspace, "demo", dry_run=False, force=False)
    assert paths_second.golden.exists()

    # With force=True the directories are recreated
    prepare_workspace(workspace, "demo", dry_run=False, force=True)


def test_mirror_golden_repo_handles_bare(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    destination = tmp_path / "workspace" / "demo" / "golden"
    destination.parent.mkdir(parents=True, exist_ok=True)

    mirror_golden_repo(bare, destination, dry_run=False, replace=True)

    assert (destination / ".git").is_dir()


def test_mirror_golden_repo_reports_failed_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    destination = tmp_path / "workspace" / "demo" / "golden"
    destination.parent.mkdir(parents=True, exist_ok=True)

    def fake_clone_repo(*_: object, **__: object) -> None:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "clone"],
            stderr="fatal: smudge filter lfs failed",
        )

    monkeypatch.setattr("repo_merger.workspace.clone_repo", fake_clone_repo)
    caplog.set_level(logging.WARNING)

    status = mirror_golden_repo(bare, destination, dry_run=False, replace=True)

    assert status == "failed"
    assert any("git clone failed" in record.message for record in caplog.records)
