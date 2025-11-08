from __future__ import annotations

import subprocess
from pathlib import Path

from repo_merger.cli import _evaluate_golden_candidate


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True)


def commit_file(path: Path, filename: str, content: str) -> None:
    file_path = path / filename
    file_path.write_text(content)
    subprocess.run(["git", "add", filename], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "commit", "-m", content], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def clone_repo_local(source: Path, destination: Path) -> None:
    subprocess.run(["git", "clone", str(source), str(destination)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_evaluate_golden_candidate_install(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    init_repo(candidate)
    commit_file(candidate, "file.txt", "initial")
    status, _ = _evaluate_golden_candidate(tmp_path / "missing", candidate)
    assert status == "install"


def test_evaluate_golden_candidate_replace(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    init_repo(origin)
    commit_file(origin, "file.txt", "initial")

    existing = tmp_path / "existing"
    clone_repo_local(origin, existing)

    candidate = tmp_path / "candidate"
    clone_repo_local(origin, candidate)
    commit_file(candidate, "file.txt", "newer")

    status, _ = _evaluate_golden_candidate(existing, candidate)
    assert status == "replace"


def test_evaluate_golden_candidate_keep(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    init_repo(origin)
    commit_file(origin, "file.txt", "initial")

    existing = tmp_path / "existing"
    clone_repo_local(origin, existing)
    commit_file(existing, "file.txt", "existing-head")

    candidate = tmp_path / "candidate"
    clone_repo_local(origin, candidate)

    status, _ = _evaluate_golden_candidate(existing, candidate)
    assert status == "keep"
