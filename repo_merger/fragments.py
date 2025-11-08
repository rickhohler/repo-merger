from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence
import shutil

from .workspace import RepoMergerError, WorkspacePaths


@dataclass
class FragmentRecord:
    fragment_id: str
    source: str
    destination: str
    source_type: str
    timestamp: str
    has_git: bool
    recovered_repo: str | None = None


def ingest_fragments(
    fragment_paths: Sequence[Path],
    workspace: WorkspacePaths,
    *,
    dry_run: bool = False,
) -> List[FragmentRecord]:
    records: List[FragmentRecord] = []
    for index, fragment in enumerate(fragment_paths, start=1):
        record = _ingest_single(fragment, index, workspace, dry_run=dry_run)
        records.append(record)

    if not dry_run:
        write_fragment_manifest(workspace.root / "fragments_manifest.json", records)
    else:
        logging.info("Dry run: manifest not written.")
    return records


def _ingest_single(
    fragment: Path,
    index: int,
    workspace: WorkspacePaths,
    *,
    dry_run: bool,
) -> FragmentRecord:
    fragment = fragment.expanduser().resolve()
    if not fragment.exists():
        raise RepoMergerError(f"Fragment path does not exist: {fragment}")

    fragment_id = _generate_fragment_id(fragment, index)
    destination = workspace.fragments / fragment_id
    source_type = _classify_fragment(fragment)
    has_git = source_type == "git"
    timestamp = datetime.now(timezone.utc).isoformat()

    if dry_run:
        logging.info(
            "Dry run: would copy fragment %s -> %s (type=%s)",
            fragment,
            destination,
            source_type,
        )
    else:
        if destination.exists():
            raise RepoMergerError(
                f"Fragment destination already exists (collision?): {destination}"
            )
        if fragment.is_dir():
            logging.info("Copying fragment directory %s -> %s", fragment, destination)
            shutil.copytree(fragment, destination, symlinks=True)
        else:
            logging.info("Copying fragment file %s -> %s", fragment, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fragment, destination)

    return FragmentRecord(
        fragment_id=fragment_id,
        source=str(fragment),
        destination=str(destination),
        source_type=source_type,
        timestamp=timestamp,
        has_git=has_git,
    )


def write_fragment_manifest(manifest_path: Path, records: Sequence[FragmentRecord]) -> None:
    payload = {"fragments": [asdict(record) for record in records]}
    manifest_path.write_text(json.dumps(payload, indent=2))
    logging.info("Wrote fragment manifest to %s", manifest_path)


def _generate_fragment_id(fragment: Path, index: int) -> str:
    slug = fragment.name or "fragment"
    slug = _sanitize(slug)
    digest = hashlib.sha1(str(fragment).encode("utf-8")).hexdigest()[:8]
    return f"{index:03d}-{slug}-{digest}"


def _classify_fragment(fragment: Path) -> str:
    if fragment.is_dir():
        git_dir = fragment / ".git"
        if git_dir.exists():
            return "git"
        return "directory"
    if fragment.is_file():
        return "file"
    return "other"


def _sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
