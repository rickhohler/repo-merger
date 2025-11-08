from __future__ import annotations

from pathlib import Path

from repo_merger.inspection import FragmentAnalysis, GitFragmentInfo
from repo_merger.merge import MergeResult
from repo_merger.reporting import summarize_cli, write_markdown_report


def test_summarize_cli_and_markdown(tmp_path: Path) -> None:
    analyses = [
        FragmentAnalysis(
            fragment_id="001-frag",
            status="diverged",
            diff_summary="modified:1 (app.txt)",
            git=GitFragmentInfo(head="abc123", branch="main", is_dirty=False, status=""),
            manifest_path="manifests/001.json",
            handlers=["handle_example"],
        )
    ]
    merges = [
        MergeResult(
            fragment_id="001-frag",
            worktree="/tmp/worktree",
            status="applied",
            message="app.txt modified",
        )
    ]

    summary = summarize_cli(analyses, merges)
    assert "Fragment Analysis Summary" in summary
    assert "Merge Results" in summary

    report_path = tmp_path / "report.md"
    write_markdown_report(report_path, analyses, merges)
    text = report_path.read_text()
    assert "**001-frag**" in text
