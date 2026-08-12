#!/usr/bin/env python3
"""Render the self-contained HTML demo dashboard.

Reads results/L2_*.json + results/figures/*.png and writes a single
HTML file (results/figures/index.html) that renders everything needed
for a demo presentation. No JavaScript frameworks, no external assets.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.microstructure.dashboard import render_dashboard

_log = logging.getLogger("render_l2_dashboard")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/figures/index.html"),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        _log.error("results dir does not exist: %s", results_dir)
        return 2

    out = render_dashboard(results_dir, Path(args.output))
    _log.info("dashboard → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
