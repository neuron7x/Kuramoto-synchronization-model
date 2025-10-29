"""Container healthcheck for the TradePulse API runtime."""

from __future__ import annotations

import importlib
import sys


def main() -> int:
    """Validate that the API server module can be imported."""

    try:
        importlib.import_module("application.runtime.server")
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"server import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script execution entrypoint
    sys.exit(main())
