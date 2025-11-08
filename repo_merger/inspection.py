from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Sequence

from .fragments import FragmentRecord
from .unhandled import UnhandledScenarioRegistry
from .workspace import RepoMergerError, WorkspacePaths


@dataclass
class GitFragmentInfo:
    head: str | None
    branch: str | None
    is_dirty: bool
    status: str


@dataclass
class FileManifestEntry:
    path: str
    size: int
    sha256: str


@dataclass
class FragmentAnalysis:
    fragment_id: str
    status: str
    diff_summary: str | None
    git: GitFragmentInfo | None
    manifest_path: str | None
    handlers: list[str] = field(default_factory=list)


def inspect_fragments(
    records: Sequence[FragmentRecord],
    workspace: WorkspacePaths,
    *,
    dry_run: bool = False,
    registry: UnhandledScenarioRegistry | None = None,
) -> List[FragmentAnalysis]:
    analyses: List[FragmentAnalysis] = []
    manifests_dir = workspace.root / "manifests"
    if not dry_run:
        manifests_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        analysis = _inspect_single(
            record,
            workspace,
            manifests_dir,
            registry,
            dry_run=dry_run,
        )
        analyses.append(analysis)

    if not dry_run:
        _write_analysis(workspace.root / "analysis.json", analyses)
    else:
        logging.info("Dry run: analysis file not written.")
    return analyses


def _inspect_single(
    record: FragmentRecord,
    workspace: WorkspacePaths,
    manifests_dir: Path,
    registry: UnhandledScenarioRegistry | None,
    *,
    dry_run: bool,
) -> FragmentAnalysis:
    fragment_path = Path(record.destination)
    handler_refs: list[str] = []
    if not fragment_path.exists():
        logging.warning("Fragment %s is missing at %s", record.fragment_id, fragment_path)
        if registry:
            handler_refs.append(
                registry.flag(
                    "missing-fragment",
                    "Fragment path missing in workspace.",
                    {"fragment_id": record.fragment_id, "path": str(fragment_path)},
                )
            )
        return FragmentAnalysis(
            fragment_id=record.fragment_id,
            status="missing",
            diff_summary=None,
            git=None,
            manifest_path=None,
            handlers=handler_refs,
        )

    comparison_path = workspace.golden
    manifest_path: Path | None = None
    git_info: GitFragmentInfo | None = None

    diff_summary, diff_status = _diff_paths(comparison_path, fragment_path)

    repo_path = _resolve_repo_path(record)
    if repo_path:
        try:
            git_info = _gather_git_info(repo_path)
        except RepoMergerError as exc:
            if registry:
                handler_refs.append(
                    registry.flag(
                        "git-inspection-error",
                        "Failed to gather git metadata for fragment.",
                        {"fragment_id": record.fragment_id, "error": str(exc)},
                    )
                )
            git_info = None
        status = "in-sync" if diff_status == "clean" else "diverged"
    else:
        if record.has_git and registry:
            handler_refs.append(
                registry.flag(
                    "git-metadata-missing",
                    "Fragment expected git metadata but none found.",
                    {"fragment_id": record.fragment_id, "path": str(fragment_path)},
                )
            )
        status = "matched" if diff_status == "clean" else "non-git"
        if not dry_run:
            manifest_path = manifests_dir / f"{record.fragment_id}.json"
            _write_manifest(manifest_path, _build_manifest(fragment_path))
        else:
            logging.info(
                "Dry run: would write manifest for fragment %s to %s",
                record.fragment_id,
                manifests_dir / f"{record.fragment_id}.json",
            )

    return FragmentAnalysis(
        fragment_id=record.fragment_id,
        status=status,
        diff_summary=diff_summary,
        git=git_info,
        manifest_path=str(manifest_path) if manifest_path else None,
        handlers=handler_refs,
    )


def _resolve_repo_path(record: FragmentRecord) -> Path | None:
    fragment_path = Path(record.destination)
    if record.recovered_repo:
        repo_path = Path(record.recovered_repo)
        if repo_path.exists():
            return repo_path
    if record.has_git and (fragment_path / ".git").exists():
        return fragment_path
    return None


def _diff_paths(golden: Path, fragment: Path) -> tuple[str | None, str]:
    golden_entries = _build_manifest(golden)
    fragment_entries = _build_manifest(fragment)

    golden_map = {entry.path: entry.sha256 for entry in golden_entries}
    fragment_map = {entry.path: entry.sha256 for entry in fragment_entries}

    added = sorted(set(fragment_map) - set(golden_map))
    removed = sorted(set(golden_map) - set(fragment_map))
    modified = sorted(
        path
        for path in set(golden_map).intersection(fragment_map)
        if golden_map[path] != fragment_map[path]
    )

    if not (added or removed or modified):
        return None, "clean"

    summary_parts = []
    if added:
        summary_parts.append(f"added:{len(added)} ({', '.join(added[:3])})")
    if removed:
        summary_parts.append(f"removed:{len(removed)} ({', '.join(removed[:3])})")
    if modified:
        summary_parts.append(f"modified:{len(modified)} ({', '.join(modified[:3])})")
    summary = "; ".join(summary_parts)
    return summary, "dirty"


def _gather_git_info(repo_path: Path) -> GitFragmentInfo:
    head = _run_git(["rev-parse", "HEAD"], repo_path, allow_failure=True)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path, allow_failure=True)
    status_output = _run_git(["status", "--short"], repo_path, allow_failure=False)
    is_dirty = bool(status_output.strip())
    return GitFragmentInfo(
        head=head.strip() if head else None,
        branch=branch.strip() if branch else None,
        is_dirty=is_dirty,
        status=status_output,
    )


def _run_git(
    args: Sequence[str],
    repo_path: Path,
    *,
    allow_failure: bool,
) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        if allow_failure:
            logging.debug("git %s failed for %s: %s", " ".join(args), repo_path, result.stderr.strip())
            return ""
        raise RepoMergerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _build_manifest(root: Path) -> List[FileManifestEntry]:
    entries: List[FileManifestEntry] = []
    for item in root.rglob("*"):
        if item.is_dir():
            continue
        if ".git" in item.parts:
            continue
        relative = item.relative_to(root)
        entries.append(
            FileManifestEntry(
                path=str(relative),
                size=item.stat().st_size,
                sha256=_sha256(item),
            )
        )
    return entries


def _write_manifest(path: Path, entries: Sequence[FileManifestEntry]) -> None:
    payload = {"files": [asdict(entry) for entry in entries]}
    path.write_text(json.dumps(payload, indent=2))


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_analysis(path: Path, analyses: Sequence[FragmentAnalysis]) -> None:
    payload = {"fragments": [asdict(analysis) for analysis in analyses]}
    path.write_text(json.dumps(payload, indent=2))
    logging.info("Wrote analysis report to %s", path)
