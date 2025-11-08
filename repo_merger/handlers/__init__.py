"""
Handler stubs for repo-merger.

Modules inside this package are auto-generated via the handler registry CLI:

    python -m repo_merger handlers add <name> --description "..."
"""

from __future__ import annotations

import importlib
import pkgutil

__all__: list[str] = []

for module_info in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
    module = importlib.import_module(f"{__name__}.{module_info.name}")
    func = getattr(module, module_info.name, None)
    if callable(func):
        globals()[module_info.name] = func
        __all__.append(module_info.name)
