#!/usr/bin/env python3
"""Regime Markov CLI — state persistence + transition matrix + dwell time."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from research.microstructure.diurnal import session_start_ms_from_frames
from research.microstructure.diurnal_filter import (
    direction_per_row,
    load_hourly_direction_map,
)
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)
from research.microstructure.regime_markov import (
    regime_markov_report,
)

_log = logging.getLogger("l2_regime_markov")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_REGIME_MARKOV.json"))
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--regime-quantile", type=float, default=0.75)
    parser.add_argument("--regime-window-sec", type=int, default=300)
    parser.add_argument("--diurnal-ic-gate", type=float, default=0.03)
    parser.add_argument("--diurnal-p-gate", type=float, default=0.05)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features
    frames = loaded.frames

    rv_score = rolling_rv_regime(features, window_rows=args.regime_window_sec)
    regime_high_mask = regime_mask_from_quantile(rv_score, quantile=args.regime_quantile)

    start_ms = session_start_ms_from_frames(frames)
    hourly_map = load_hourly_direction_map(
        Path(args.diurnal_filter),
        ic_gate=float(args.diurnal_ic_gate),
        pvalue_gate=float(args.diurnal_p_gate),
    )
    dpr = direction_per_row(hourly_map, start_ms=start_ms, n_rows=features.n_rows)

    report = regime_markov_report(regime_high_mask, dpr)
    payload = asdict(report)
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)
    _log.info(
        "mean_diagonal=%.4f  n_transitions=%d",
        report.mean_diagonal,
        report.n_transitions,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
