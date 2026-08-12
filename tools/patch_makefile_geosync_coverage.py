#!/usr/bin/env python3
"""Patch Makefile coverage shortcuts to include the geosync package."""

from __future__ import annotations

import argparse
from pathlib import Path

OLD = "--cov=core --cov=backtest --cov=execution"
NEW = "--cov=core --cov=backtest --cov=execution --cov=geosync"
GEOSYNC_COV = "--cov=geosync"
EXPECTED_REPLACEMENTS = 3


def patch_text(text: str) -> tuple[str, int]:
    # OLD is a prefix of NEW, so a naive re-replace would corrupt an
    # already-aligned Makefile (--cov=geosync --cov=geosync). Use the
    # geosync marker as the idempotency signal: once present, no-op.
    if GEOSYNC_COV in text:
        return text, 0
    return text.replace(OLD, NEW), text.count(OLD)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Align Makefile coverage shortcuts with geosync surface"
    )
    parser.add_argument("path", nargs="?", default="Makefile", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    text = args.path.read_text(encoding="utf-8")
    already = GEOSYNC_COV in text
    patched, count = patch_text(text)

    if not already and OLD in text and count != EXPECTED_REPLACEMENTS:
        print(f"unexpected_replacement_count:{count}")
        return 2

    if args.check:
        if already:
            print("ok")
            return 0
        if OLD in text:
            print(f"needs_patch:{count}")
            return 1
        print("missing_geosync_coverage")
        return 1

    if patched != text:
        args.path.write_text(patched, encoding="utf-8")
        print(f"patched:{count}")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
