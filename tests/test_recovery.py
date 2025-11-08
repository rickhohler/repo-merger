from __future__ import annotations

from pathlib import Path

from repo_merger.fragments import ingest_fragments
from repo_merger.recovery import recover_fragments
from repo_merger.workspace import prepare_workspace


def test_recover_fragment_creates_git_repo(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path / "workspace", "demo", dry_run=False, force=False)
    fragment = tmp_path / "fragment"
    fragment.mkdir()
    (fragment / "file.txt").write_text("content")

    records = ingest_fragments([fragment], workspace, dry_run=False)

    results = recover_fragments(records, workspace, dry_run=False)

    assert results
    recovered_path = Path(results[0].recovered_path)
    assert (recovered_path / ".git").exists()
