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
from repo_merger.cli import _log_scan_summary, _write_scan_status_files


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
    context = ScanContext(
        manifest=manifest,
        report_path=workspace / "scan_report.json",
        source_identifier="test-source",
    )
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


def test_write_scan_status_files_accumulates(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    success_paths = [tmp_path / "done-a", tmp_path / "done-b"]
    failure_paths = [tmp_path / "failed-a"]
    source_identifier = "usb-drive"

    _write_scan_status_files(
        workspace,
        success_paths=success_paths,
        failure_paths=failure_paths,
        source_identifier=source_identifier,
    )

    succeeded = sorted((workspace / "scan_succeeded.txt").read_text().splitlines())
    failed = sorted((workspace / "scan_failed.txt").read_text().splitlines())

    expected_success = sorted(
        f"{source_identifier}:{path}" for path in success_paths
    )
    expected_failure = sorted(
        f"{source_identifier}:{path}" for path in failure_paths
    )
    assert succeeded == expected_success
    assert failed == expected_failure

    extra_success = [tmp_path / "done-a", tmp_path / "done-c"]
    _write_scan_status_files(
        workspace,
        success_paths=extra_success,
        failure_paths=[],
        source_identifier=source_identifier,
    )

    resumed = sorted((workspace / "scan_succeeded.txt").read_text().splitlines())
    expected_combined = sorted(
        {
            f"{source_identifier}:{path}"
            for path in success_paths + extra_success
        }
    )
    assert resumed == expected_combined
