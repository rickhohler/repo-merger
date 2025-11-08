from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
import subprocess

import pytest

from repo_merger.auto import (
    ScanCandidate,
    ScanContext,
    ScanManifest,
    ScanReportEntry,
    scan_for_repos,
)
from repo_merger.cli import _log_scan_summary


def make_git_repo(path: Path, has_remote: bool = True) -> None:
    git_dir = path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    config = git_dir / "config"
    if has_remote:
        config.write_text('[remote "origin"]\nurl = git@example.com:demo/repo.git\n')
    else:
        config.write_text("[core]\n\trepositoryformatversion = 0\n")


def test_scan_for_repos_classifies_golden_and_fragment(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    golden = source / "proj-golden"
    golden.mkdir()
    make_git_repo(golden)
    fragment = source / "fragment-alpha"
    fragment.mkdir()
    (fragment / "file.txt").write_text("sample")

    candidates = scan_for_repos(
        source,
        golden_pattern="*golden",
        fragment_pattern="fragment*",
    )
    assert {c.classification for c in candidates} == {"golden", "fragment"}


def test_scan_detects_bare_golden(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    bare = source / "proj.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    candidates = scan_for_repos(
        source,
        golden_pattern="*",
        fragment_pattern="fragment*",
    )

    bare_candidate = next((c for c in candidates if c.path == bare), None)
    assert bare_candidate is not None
    assert bare_candidate.classification == "golden"


def test_scan_manifest_records_ingestion(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    fragment = source / "fragment-alpha"
    fragment.mkdir()
    (fragment / "data.txt").write_text("content")

    candidates = scan_for_repos(
        source,
        golden_pattern="*golden",
        fragment_pattern="fragment*",
    )
    candidate = next(c for c in candidates if c.classification == "fragment")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest = ScanManifest(workspace / "scan_manifest.json")
    context = ScanContext(manifest=manifest, report_path=workspace / "scan_report.json")
    context.add_pending_fragment(candidate)
    context.add_report_entry(
        ScanReportEntry(
            source=str(candidate.path),
            classification="fragment",
            confidence=1.0,
            action="ingest",
            reason="test",
        )
    )

    class DummyRecord:
        def __init__(self, source: str, fragment_id: str, destination: str) -> None:
            self.source = source
            self.fragment_id = fragment_id
            self.destination = destination

    record = DummyRecord(
        source=str(candidate.path),
        fragment_id="001-fragment-hash",
        destination=str(workspace / "fragments" / "001-fragment-hash"),
    )
    context.finalize_ingestion([record], identifier="demo", dry_run=False)

    reloaded = ScanManifest(workspace / "scan_manifest.json")
    entry = reloaded.lookup(candidate.path)
    assert entry is not None
    assert entry["fragment_id"] == "001-fragment-hash"
    assert entry["digest"] == candidate.digest


def test_log_scan_summary_reports_failed_goldens(caplog: pytest.LogCaptureFixture) -> None:
    stats = Counter({"goldens": 1, "golden-failed": 1})
    caplog.set_level(logging.INFO)

    _log_scan_summary(stats, dry_run=False)

    assert "Goldens failed" in caplog.text
