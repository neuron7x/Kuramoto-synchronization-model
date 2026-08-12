#!/usr/bin/env python3
"""Diff-bound falsifier for the ricci-microstructure-v1-docs acceptor.

Inverts the honesty contract of the lane documentation: NEGATIVE_RESULTS.md MUST
keep the negative-result framing ("successful falsification") and the lane docs
MUST NOT contain any forbidden market-mythology promotion token. Rewriting
NEGATIVE_RESULTS.md to drop the falsification framing, or injecting an
ALPHA_FOUND-style promotion into the docs, flips this script to a non-zero exit.

Exit 0  -> docs preserve the negative framing and carry no overclaim token.
Exit 1  -> negative framing dropped, or a forbidden promotion token is present.
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN = ("ALPHA_FOUND", "MARKET_SIGNAL_PROVEN", "PRODUCTION_READY", "PHYSICS_CONFIRMED")
DOCS = (
    Path("docs/NEGATIVE_RESULTS.md"),
    Path("docs/RICCI_MICROSTRUCTURE.md"),
    Path("docs/REPRODUCIBILITY.md"),
)


def main() -> int:
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                print(f"FALSIFIED: forbidden promotion token {token!r} in {doc}", file=sys.stderr)
                return 1
    negatives = Path("docs/NEGATIVE_RESULTS.md").read_text(encoding="utf-8")
    if "successful falsification" not in negatives:
        print("FALSIFIED: NEGATIVE_RESULTS.md dropped the falsification framing", file=sys.stderr)
        return 1
    print("OK: lane docs preserve the negative framing and carry no overclaim token")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
