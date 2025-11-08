from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Sequence

from .gitutils import has_git_dir, has_remote_from_config, is_bare_repo, read_git_config
from .workspace import RepoMergerError

ScanClassification = Literal["golden", "fragment", "unknown"]


@dataclass
class ScanCandidate:
    path: Path
    classification: ScanClassification
    confidence: float
    reason: str
    digest: str


@dataclass
class ScanReportEntry:
    source: str
    classification: ScanClassification
    confidence: float
    action: str
    reason: str
    fragment_id: str | None = None
    destination: str | None = None


class ScanManifest:
    def __init__(self, manifest_path: Path) -> None:
        self.path = manifest_path
        self.entries: Dict[str, Dict[str, str]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return
        for entry in data.get("entries", []):
            self.entries[entry["source"]] = entry

    def lookup(self, source: Path) -> Dict[str, str] | None:
        return self.entries.get(str(source))

    def record_fragment(
        self,
        *,
        source: Path,
        digest: str,
        fragment_id: str,
        destination: Path,
        identifier: str,
    ) -> None:
        self.entries[str(source)] = {
            "source": str(source),
            "type": "fragment",
            "identifier": identifier,
            "fragment_id": fragment_id,
            "digest": digest,
            "destination": str(destination),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        payload = {"entries": list(self.entries.values())}
        self.path.write_text(json.dumps(payload, indent=2))
        self._dirty = False


@dataclass
class ScanContext:
    manifest: ScanManifest
    report_path: Path
    report_entries: List[ScanReportEntry] = field(default_factory=list)
    pending_fragments: Dict[str, ScanCandidate] = field(default_factory=dict)

    def add_report_entry(self, entry: ScanReportEntry) -> None:
        self.report_entries.append(entry)

    def add_pending_fragment(self, candidate: ScanCandidate) -> None:
        self.pending_fragments[str(candidate.path)] = candidate

    def fragments_to_ingest(self) -> List[Path]:
        return [Path(src) for src in self.pending_fragments.keys()]

    def finalize_ingestion(self, records: Sequence, *, identifier: str, dry_run: bool) -> None:
        if dry_run:
            for entry in self.report_entries:
                if entry.action == "ingest":
                    entry.action = "dry-run"
            return

        for record in records:
            candidate = self.pending_fragments.get(record.source)
            if not candidate:
                continue
            self.manifest.record_fragment(
                source=Path(record.source),
                digest=candidate.digest,
                fragment_id=record.fragment_id,
                destination=Path(record.destination),
                identifier=identifier,
            )
            for entry in self.report_entries:
                if entry.source == record.source:
                    entry.action = "ingested"
                    entry.fragment_id = record.fragment_id
                    entry.destination = record.destination
        self.manifest.save()
        self._write_report()

    def _write_report(self) -> None:
        payload = {"entries": [entry.__dict__ for entry in self.report_entries]}
        self.report_path.write_text(json.dumps(payload, indent=2))


def scan_for_repos(
    source_dir: Path,
    *,
    golden_pattern: str,
    fragment_pattern: str,
    exclude: Iterable[Path] | None = None,
) -> List[ScanCandidate]:
    source_dir = source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise RepoMergerError(f"Scan source does not exist: {source_dir}")

    exclude_paths = {path.expanduser().resolve() for path in (exclude or [])}
    candidates: List[ScanCandidate] = []

    for root, dirs, _ in os.walk(source_dir):
        current = Path(root)
        if any(current == ex or ex in current.parents for ex in exclude_paths):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in {".git", ".hg", ".svn"}]
        if not _looks_like_repo(current, golden_pattern, fragment_pattern):
            continue
        classification, confidence, reason = _classify_repo(
            current, golden_pattern, fragment_pattern
        )
        if classification == "unknown":
            continue
        digest = _hash_directory(current)
        candidates.append(
            ScanCandidate(
                path=current,
                classification=classification,
                confidence=confidence,
                reason=reason,
                digest=digest,
            )
        )
    return candidates


def _looks_like_repo(path: Path, golden_pattern: str, fragment_pattern: str) -> bool:
    name = path.name
    if fnmatch(name, golden_pattern) or fnmatch(name, fragment_pattern):
        return True
    return has_git_dir(path) or is_bare_repo(path)


def _classify_repo(
    path: Path,
    golden_pattern: str,
    fragment_pattern: str,
) -> tuple[ScanClassification, float, str]:
    score_golden = 0
    score_fragment = 0
    reasons: List[str] = []

    name = path.name
    if fnmatch(name, golden_pattern):
        score_golden += 2
        reasons.append("name-matches-golden-pattern")
    if fnmatch(name, fragment_pattern):
        score_fragment += 1
        reasons.append("name-matches-fragment-pattern")

    git_dir = path / ".git"
    if git_dir.is_dir():
        score_golden += 2
        config_text = read_git_config(git_dir / "config")
        if has_remote_from_config(config_text):
            score_golden += 1
            reasons.append("git-remote-found")
        else:
            score_fragment += 1
            reasons.append("git-metadata-no-remote")
    elif is_bare_repo(path):
        score_golden += 3
        config_text = read_git_config(path / "config")
        if has_remote_from_config(config_text):
            score_golden += 1
            reasons.append("bare-repo-with-remote")
        else:
            reasons.append("bare-repo")
    else:
        score_fragment += 1
        reasons.append("missing-git-directory")

    if score_golden - score_fragment >= 1:
        classification: ScanClassification = "golden"
    elif score_fragment - score_golden >= 0:
        classification = "fragment"
    else:
        classification = "unknown"

    confidence = min(1.0, abs(score_golden - score_fragment) / 4.0)
    reason = ",".join(reasons) or "no-heuristics"
    return classification, confidence, reason


def _hash_directory(path: Path) -> str:
    hasher = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path)
        hasher.update(str(rel).encode("utf-8"))
        stat = file_path.stat()
        hasher.update(str(stat.st_size).encode("utf-8"))
        hasher.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
    return hasher.hexdigest()
