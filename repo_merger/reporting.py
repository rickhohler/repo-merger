from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Sequence

from .inspection import FragmentAnalysis
from .merge import MergeResult


def load_analysis(path: Path) -> Sequence[FragmentAnalysis]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    analyses = []
    for entry in data.get("fragments", []):
        analyses.append(FragmentAnalysis(**entry))
    return analyses


def load_merge_report(path: Path) -> Sequence[MergeResult]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    results = []
    for entry in data.get("merges", []):
        results.append(MergeResult(**entry))
    return results


def summarize_cli(
    analyses: Sequence[FragmentAnalysis],
    merges: Sequence[MergeResult] | None = None,
) -> str:
    lines = []
    lines.append("Fragment Analysis Summary")
    lines.append("========================")
    for analysis in analyses:
        detail = f"- {analysis.fragment_id}: {analysis.status}"
        if analysis.diff_summary:
            detail += f" ({analysis.diff_summary})"
        if analysis.handlers:
            detail += f" [handlers: {', '.join(analysis.handlers)}]"
        lines.append(detail)
    if merges:
        lines.append("")
        lines.append("Merge Results")
        lines.append("=============")
        for result in merges:
            lines.append(f"- {result.fragment_id}: {result.status} ({result.message})")
    return "\n".join(lines)


def write_markdown_report(
    output_path: Path,
    analyses: Sequence[FragmentAnalysis],
    merges: Sequence[MergeResult] | None = None,
) -> None:
    lines = ["# Repo Merger Report", ""]

    lines.append("## Fragment Status")
    lines.append("")
    for analysis in analyses:
        lines.append(f"- **{analysis.fragment_id}** — {analysis.status}")
        if analysis.git:
            lines.append(
                f"  - HEAD: `{analysis.git.head}` | Branch: `{analysis.git.branch}` | Dirty: {analysis.git.is_dirty}"
            )
        if analysis.diff_summary:
            lines.append(f"  - Diff: {analysis.diff_summary}")
        if analysis.manifest_path:
            lines.append(f"  - Manifest: `{analysis.manifest_path}`")
        if analysis.handlers:
            lines.append(f"  - Handlers: {', '.join(f'`{h}`' for h in analysis.handlers)}")
        lines.append("")

    if merges:
        lines.append("## Merge Results")
        lines.append("")
        for result in merges:
            lines.append(f"- **{result.fragment_id}** — {result.status}")
            lines.append(f"  - Worktree: `{result.worktree}`")
            if result.message:
                lines.append(f"  - Notes: {result.message}")
            lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n")
    logging.info("Wrote report to %s", output_path)
