from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_merger.fragments import ingest_fragments
from repo_merger.workspace import RepoMergerError, WorkspacePaths, prepare_workspace


def setup_workspace(tmp_path: Path) -> WorkspacePaths:
    golden_src = tmp_path / "golden-src"
    golden_src.mkdir()
    return prepare_workspace(tmp_path / "workspace", "demo", dry_run=False, force=False)


def test_ingest_fragment_directory(tmp_path: Path) -> None:
    paths = setup_workspace(tmp_path)
    fragment = tmp_path / "fragment-a"
    fragment.mkdir()
    (fragment / "file.txt").write_text("alpha")

    records = ingest_fragments([fragment], paths, dry_run=False)

    assert len(records) == 1
    dest = Path(records[0].destination)
    assert dest.exists()
    assert (dest / "file.txt").read_text() == "alpha"
    assert records[0].copied is True

    manifest_path = paths.root / "fragments_manifest.json"
    data = json.loads(manifest_path.read_text())
    assert len(data["fragments"]) == 1
    assert data["fragments"][0]["fragment_id"] == records[0].fragment_id


def test_ingest_fragment_dry_run(tmp_path: Path) -> None:
    paths = setup_workspace(tmp_path)
    fragment = tmp_path / "fragment-b"
    fragment.mkdir()

    records = ingest_fragments([fragment], paths, dry_run=True)

    assert len(records) == 1
    assert not Path(records[0].destination).exists()
    assert records[0].copied is False
    assert not (paths.root / "fragments_manifest.json").exists()


def test_ingest_missing_fragment_errors(tmp_path: Path) -> None:
    paths = setup_workspace(tmp_path)
    missing = tmp_path / "missing"

    with pytest.raises(RepoMergerError):
        ingest_fragments([missing], paths, dry_run=False)


def test_ingest_fragment_existing_destination_is_reused(tmp_path: Path) -> None:
    paths = setup_workspace(tmp_path)
    fragment = tmp_path / "fragment-c"
    fragment.mkdir()
    (fragment / "file.txt").write_text("gamma")

    first = ingest_fragments([fragment], paths, dry_run=False)
    assert first[0].copied is True

    # Re-run ingestion with the same fragment; destination already populated.
    second = ingest_fragments([fragment], paths, dry_run=False)
    assert second[0].destination == first[0].destination
    assert second[0].copied is False
