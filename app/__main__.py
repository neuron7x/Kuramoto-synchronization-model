"""Module execution entrypoint for ``python -m app``."""

from __future__ import annotations

from . import run


if __name__ == "__main__":  # pragma: no cover - CLI shim
    run()
