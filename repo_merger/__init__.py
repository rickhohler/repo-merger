"""
repo_merger package

Provides the CLI entrypoint (`python -m repo_merger`) and supporting helpers
for preparing the golden/fragments workspace.
"""

from .cli import main

__all__ = ["main"]
