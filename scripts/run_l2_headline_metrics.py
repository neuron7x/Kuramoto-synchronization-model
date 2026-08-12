#!/usr/bin/env python3
"""Render the consolidated headline metrics JSON.

Reads the scattered results/L2_*.json artifacts and emits a single
flat primitive-valued file at results/L2_HEADLINE_METRICS.json that
downstream tooling can ingest without parsing variable structures.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.microstructure.headline_metrics import write_headline_metrics

_log = logging.getLogger("l2_headline_metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/L2_HEADLINE_METRICS.json"),
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

    out = write_headline_metrics(results_dir, Path(args.output))
    _log.info("headline metrics → %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
