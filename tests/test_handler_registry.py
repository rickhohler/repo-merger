from __future__ import annotations

from pathlib import Path

from repo_merger.handler_registry import HandlerRegistry


def prepare_repo_root(tmp_path: Path) -> Path:
    (tmp_path / "repo_merger" / "handlers").mkdir(parents=True)
    (tmp_path / "tests").mkdir(parents=True)
    return tmp_path


def test_add_handler_creates_artifacts(tmp_path: Path) -> None:
    repo_root = prepare_repo_root(tmp_path)
    registry = HandlerRegistry(repo_root)

    meta = registry.add_handler("sample-handler", "Sample description")

    handler_file = repo_root / "repo_merger" / "handlers" / f"{meta.name}.py"
    doc_file = repo_root / "HANDLERS.md"
    test_file = repo_root / "tests" / "handlers" / f"test_{meta.name}.py"
    manifest = repo_root / "handlers_registry.json"

    assert handler_file.exists()
    assert doc_file.exists()
    assert test_file.exists()
    assert manifest.exists()

    text = doc_file.read_text()
    assert meta.name in text


def test_ensure_handler_returns_existing(tmp_path: Path) -> None:
    repo_root = prepare_repo_root(tmp_path)
    registry = HandlerRegistry(repo_root)

    meta_a = registry.ensure_handler("duplicate-handler", "First description")
    meta_b = registry.ensure_handler("duplicate-handler", "Second description")

    assert meta_a.name == meta_b.name
