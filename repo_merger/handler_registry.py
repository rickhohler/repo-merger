from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


@dataclass
class HandlerMeta:
    name: str
    description: str
    status: str = "TODO"
    doc_path: str = "HANDLERS.md"


class HandlerRegistry:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.registry_path = repo_root / "handlers_registry.json"
        self.handlers_dir = repo_root / "repo_merger" / "handlers"
        self.docs_path = repo_root / "HANDLERS.md"
        self.tests_dir = repo_root / "tests" / "handlers"

        self._handlers: Dict[str, HandlerMeta] = {}
        self._load()

    # Public API -----------------------------------------------------------
    def list_handlers(self) -> List[HandlerMeta]:
        return list(self._handlers.values())

    def add_handler(self, name: str, description: str) -> HandlerMeta:
        handler_name = self._build_handler_name(name)
        if handler_name in self._handlers:
            raise ValueError(f"Handler '{handler_name}' already exists.")

        meta = HandlerMeta(name=handler_name, description=description)
        self._handlers[handler_name] = meta
        self._write_stub(meta)
        self._update_docs(meta)
        self._write_test_stub(meta)
        self._save()
        logging.info("Added handler stub %s", handler_name)
        return meta

    def ensure_handler(self, name: str, description: str) -> HandlerMeta:
        handler_name = self._build_handler_name(name)
        if handler_name in self._handlers:
            return self._handlers[handler_name]
        return self.add_handler(name, description)

    def get_handler(self, handler_name: str) -> HandlerMeta | None:
        return self._handlers.get(handler_name)

    # Internal helpers -----------------------------------------------------
    def _load(self) -> None:
        if not self.registry_path.exists():
            return
        data = json.loads(self.registry_path.read_text())
        for entry in data.get("handlers", []):
            self._handlers[entry["name"]] = HandlerMeta(**entry)

    def _save(self) -> None:
        payload = {"handlers": [asdict(meta) for meta in self._handlers.values()]}
        self.registry_path.write_text(json.dumps(payload, indent=2))

    def _write_stub(self, meta: HandlerMeta) -> None:
        self.handlers_dir.mkdir(parents=True, exist_ok=True)
        stub_path = self.handlers_dir / f"{meta.name}.py"
        if stub_path.exists():
            logging.debug("Handler stub already exists at %s", stub_path)
            return
        stub_path.write_text(
            (
                f'"""\nAuto-generated handler stub: {meta.name}\n"""\n\n'
                "from __future__ import annotations\n\n"
                f"def {meta.name}(context: dict | None = None) -> None:\n"
                f'    \"\"\"{meta.description} (status: {meta.status}).\"\"\"\n'
                f"    raise NotImplementedError(\"Handler '{meta.name}' not implemented yet\")\n"
            )
        )

    def _update_docs(self, meta: HandlerMeta) -> None:
        if not self.docs_path.exists():
            self.docs_path.write_text("# Handler Catalog\n\n")
        lines = self.docs_path.read_text().splitlines()
        entry = f"- **{meta.name}** — {meta.description} _(status: {meta.status})_"
        if entry not in lines:
            lines.append(entry)
            self.docs_path.write_text("\n".join(lines) + "\n")

    def _write_test_stub(self, meta: HandlerMeta) -> None:
        self.tests_dir.mkdir(parents=True, exist_ok=True)
        test_path = self.tests_dir / f"test_{meta.name}.py"
        if test_path.exists():
            return
        test_path.write_text(
            (
                f"from repo_merger.handlers import {meta.name}\n\n"
                f"def test_{meta.name}_stub() -> None:\n"
                f"    try:\n"
                f"        {meta.name}()\n"
                f"    except NotImplementedError:\n"
                f"        pass\n"
            )
        )

    @staticmethod
    def _sanitize_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "handler"

    def _build_handler_name(self, raw: str) -> str:
        slug = self._sanitize_name(raw)
        if slug.startswith("handle_"):
            return slug
        return f"handle_{slug}"
