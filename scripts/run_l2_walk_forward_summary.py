#!/usr/bin/env python3
"""Walk-forward temporal stability summary CLI.

Reads results/L2_WALK_FORWARD.json (produced by the pre-existing
walk-forward runner) and writes results/L2_WALK_FORWARD_SUMMARY.json
with a single-verdict temporal-stability report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from research.microstructure.walk_forward import summarize_walk_forward

_log = logging.getLogger("l2_wf_summary")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/L2_WALK_FORWARD.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/L2_WALK_FORWARD_SUMMARY.json"),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not Path(args.input).exists():
        _log.error("walk-forward input missing: %s", args.input)
        return 2

    summary = summarize_walk_forward(Path(args.input))
    payload = asdict(summary)
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "walk-forward: %d/%d valid  IC mean=%.4f median=%.4f  %% pos=%.1f%%  verdict=%s",
        summary.n_valid,
        summary.n_windows,
        summary.ic_mean,
        summary.ic_median,
        100.0 * summary.fraction_positive,
        summary.verdict,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
