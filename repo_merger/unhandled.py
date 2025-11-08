from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .handler_registry import HandlerRegistry


@dataclass
class UnhandledScenario:
    handler: str
    description: str
    context: Dict[str, str] = field(default_factory=dict)


class UnhandledScenarioRegistry:
    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.registry = HandlerRegistry(self.repo_root)
        self.entries: List[UnhandledScenario] = []

    def flag(
        self,
        handler_slug: str,
        description: str,
        context: Optional[Dict[str, str]] = None,
    ) -> str:
        meta = self.registry.ensure_handler(handler_slug, description)
        entry = UnhandledScenario(
            handler=meta.name,
            description=description,
            context=context or {},
        )
        self.entries.append(entry)
        logging.warning(
            "Unhandled scenario '%s' captured. Handler stub: %s", description, meta.name
        )
        return meta.name

    def to_dict(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            "scenarios": [
                {
                    "handler": entry.handler,
                    "description": entry.description,
                    "context": entry.context,
                }
                for entry in self.entries
            ]
        }
