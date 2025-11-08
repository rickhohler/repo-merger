from __future__ import annotations

import configparser
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .gitutils import clone_repo, is_bare_repo

class RepoMergerError(Exception):
    """Base exception for workspace preparation errors."""


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    golden: Path
    fragments: Path


def derive_identifier(golden_path: Path, explicit: Optional[str] = None) -> str:
    if explicit:
        return _sanitize(explicit)

    config_path = _resolve_git_config(golden_path)
    if config_path and config_path.is_file():
        identifier = _identifier_from_config(config_path)
        if identifier:
            return identifier

    fallback = golden_path.name or "workspace"
    return _sanitize(fallback)


def sanitize_identifier(value: str) -> str:
    return _sanitize(value)


def ensure_workspace_dirs(workspace_root: Path, identifier: str) -> WorkspacePaths:
    workspace_root = workspace_root.expanduser()
    root = workspace_root / identifier
    golden_dir = root / "golden"
    fragments_dir = root / "fragments"
    for path in [workspace_root, root, golden_dir, fragments_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return WorkspacePaths(root=root, golden=golden_dir, fragments=fragments_dir)


def prepare_workspace(
    workspace_root: Path,
    identifier: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> WorkspacePaths:
    workspace_root = workspace_root.expanduser()
    _ensure_directory(workspace_root, dry_run=dry_run)

    target_root = workspace_root / identifier
    _ensure_directory_state(target_root, dry_run=dry_run, force=force, describe="workspace root")

    golden_dir = target_root / "golden"
    fragments_dir = target_root / "fragments"

    _ensure_directory_state(golden_dir, dry_run=dry_run, force=force, describe="golden directory")
    _ensure_directory_state(
        fragments_dir, dry_run=dry_run, force=force, describe="fragments directory"
    )

    return WorkspacePaths(root=target_root, golden=golden_dir, fragments=fragments_dir)


def mirror_golden_repo(
    source: Path,
    destination: Path,
    *,
    dry_run: bool = False,
    replace: bool = False,
) -> None:
    source = source.expanduser()
    if not source.exists():
        raise RepoMergerError(f"Golden repository path does not exist: {source}")

    if dry_run:
        logging.info("Dry run: would mirror %s -> %s", source, destination)
        return

    if destination.exists():
        if not destination.is_dir():
            raise RepoMergerError(
                f"Golden destination exists but is not a directory: {destination}"
            )
        if any(destination.iterdir()):
            if replace:
                shutil.rmtree(destination)
            else:
                logging.info(
                    "Golden destination already populated at %s; skipping mirror.", destination
                )
                return

    if destination.exists():
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    if is_bare_repo(source):
        logging.info("Cloning bare repository from %s", source)
        try:
            clone_repo(source, destination)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - rare
            raise RepoMergerError(
                f"git clone failed for bare repository {source}: {exc.stderr.strip()}"
            ) from exc
    else:
        logging.info("Copying golden repository into %s", destination)
        shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)


def _identifier_from_config(config_path: Path) -> Optional[str]:
    parser = configparser.ConfigParser()
    parser.read(config_path)
    remote_section = 'remote "origin"'
    if remote_section not in parser:
        return None
    url = parser[remote_section].get("url")
    if not url:
        return None
    identifier = _slug_from_remote(url)
    return _sanitize(identifier) if identifier else None


def _slug_from_remote(url: str) -> str:
    cleaned = url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    cleaned = cleaned.replace(":", "/")
    parts = [segment for segment in cleaned.split("/") if segment]
    if not parts:
        return "workspace"
    repo = parts[-1]
    owner = parts[-2] if len(parts) >= 2 else None
    if owner and "@" in owner:
        owner = owner.split("@")[-1]
    slug = f"{owner}-{repo}" if owner else repo
    return slug


def _sanitize(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return sanitized or "workspace"


def _resolve_git_config(golden_path: Path) -> Optional[Path]:
    git_dir = golden_path / ".git"
    if git_dir.is_dir():
        config = git_dir / "config"
        if config.is_file():
            return config
    if git_dir.is_file():
        pointer = git_dir.read_text().strip()
        if pointer.startswith("gitdir:"):
            gitdir = pointer.split(":", 1)[1].strip()
            candidate = (golden_path / gitdir).expanduser()
            config = candidate / "config"
            if config.is_file():
                return config
    bare_config = golden_path / "config"
    if bare_config.is_file():
        return bare_config
    return None


def _ensure_directory(path: Path, *, dry_run: bool) -> None:
    if path.exists():
        return
    if dry_run:
        logging.info("Dry run: would create directory %s", path)
    else:
        path.mkdir(parents=True, exist_ok=True)


def _ensure_directory_state(
    path: Path, *, dry_run: bool, force: bool, describe: str
) -> None:
    if path.exists():
        if not path.is_dir():
            raise RepoMergerError(f"Existing {describe} is not a directory: {path}")
        if not force:
            logging.debug("Reusing existing %s at %s", describe, path)
            return
        if dry_run:
            logging.info("Dry run: would remove existing %s at %s", describe, path)
            return
        shutil.rmtree(path)
    if dry_run:
        logging.info("Dry run: would create %s at %s", describe, path)
    else:
        path.mkdir(parents=True, exist_ok=True)
