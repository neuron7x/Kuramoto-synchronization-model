"""Utility scripts bundled with the TradePulse repository.

This package is imported in a variety of contexts ranging from lightweight
command-line helpers (for example ``python -m scripts.db_migrate``) to the
full developer tooling entry point exposed via :mod:`scripts.cli`. Importing
``scripts.cli`` pulls in a significant portion of the application which in
turn expects numerous environment variables to be present. Eagerly importing
``scripts.cli`` from :mod:`scripts.__init__` therefore made seemingly unrelated
helpers crash at import time when optional secrets were not configured.

To keep the package import side-effect free we lazily resolve ``main`` only
when it is actually requested. This mirrors the previous public API while
ensuring the ``scripts`` package can be safely imported in minimal
environments, including test suites that exercise individual helper modules.
"""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from importlib import import_module
from typing import Any

__all__ = ["main"]


def __getattr__(name: str) -> Any:
    """Lazily expose ``main`` without importing the heavy CLI stack."""

    if name == "main":
        return import_module("scripts.cli").main
    raise AttributeError(f"module 'scripts' has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - trivial helper
    """Advertise the lazily provided attributes for ``dir()`` callers."""

    return sorted(set(globals()) | {"main"})


if False:  # pragma: no cover - aid static type checkers without side effects
    from .cli import main as main  # noqa: F401
