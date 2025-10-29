"""Wrapper around the legacy application runtime entrypoint."""

from __future__ import annotations

from application.runtime.server import run


def main() -> None:
    """Invoke the production API server entrypoint."""

    run()


if __name__ == "__main__":  # pragma: no cover - module CLI entrypoint
    main()
