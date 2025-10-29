"""Module entrypoint delegating to :mod:`app.main`."""

from __future__ import annotations

from .main import main

if __name__ == "__main__":  # pragma: no cover - executed by the interpreter
    main()
