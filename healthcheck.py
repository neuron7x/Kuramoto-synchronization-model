"""Container health check ensuring TradePulse dependencies import correctly."""

from __future__ import annotations

import importlib
import sys
from typing import Final

_MODULES: Final[tuple[str, ...]] = (
    "interfaces.cli",
    "core",
    "backtest",
)


def main() -> int:
    """Return ``0`` when critical modules import without errors."""

    for module in _MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - executed in container healthcheck
            print(f"failed to import {module}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
