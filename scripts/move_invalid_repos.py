#!/usr/bin/env python3
"""Move invalid golden/fragment trees into a dedicated save location."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace_root", type=Path, help="Workspace root containing golden/fragments directories")
    parser.add_argument(
        "--save-root",
        type=Path,
        help="Where to stash the invalid directories (default: <workspace_root>/invalid-save)",
    )
    return parser.parse_args()


def is_valid_git(path: Path) -> bool:
    try:
        subprocess.run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def relocate(path: Path, workspace_root: Path, save_root: Path) -> Path:
    relative = path.relative_to(workspace_root)
    target = save_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        stamp = time.strftime("%Y%m%d%H%M%S")
        target = target.with_name(f"{target.name}-{stamp}")
    shutil.move(str(path), str(target))
    return target


def main() -> None:
    args = parse_args()
    workspace_root = args.workspace_root.expanduser().resolve()
    if not workspace_root.exists():
        sys.exit(f"workspace does not exist: {workspace_root}")

    save_root = (args.save_root or (workspace_root / "invalid-save")).expanduser().resolve()
    save_root.mkdir(parents=True, exist_ok=True)

    invalid_golden = []
    invalid_fragments = []

    for workspace_dir in sorted(workspace_root.iterdir()):
        if not workspace_dir.is_dir():
            continue
        golden = workspace_dir / "golden"
        if golden.exists():
            if not is_valid_git(golden):
                target = relocate(golden, workspace_root, save_root)
                invalid_golden.append((golden, target))
        fragments = workspace_dir / "fragments"
        if not fragments.exists():
            continue
        for fragment in sorted(fragments.iterdir()):
            if not fragment.is_dir() or fragment.name.startswith("."):
                continue
            if not is_valid_git(fragment):
                target = relocate(fragment, workspace_root, save_root)
                invalid_fragments.append((fragment, target))

    print("Moved invalid golden directories:")
    for src, dst in invalid_golden:
        print(f"  {src} -> {dst}")
    print("\nMoved invalid fragment directories:")
    for src, dst in invalid_fragments:
        print(f"  {src} -> {dst}")
    print(f"\nTotals: {len(invalid_golden)} golden, {len(invalid_fragments)} fragments relocated")


if __name__ == "__main__":
    main()
