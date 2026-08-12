#!/usr/bin/env python3
"""Hyperparameter ablation sweep for the break-even maker gate.

Perturbs the two most consequential knobs of the REGIME_Q75+DIURNAL
strategy and records how the break-even maker-fraction gate shifts:

    * regime_quantile ∈ {0.70, 0.75, 0.80}
    * regime_window_sec ∈ {180, 300, 450}

For each combination we re-run the cost sweep and interpolate the
break-even maker fraction. Writes results/L2_ABLATION_SENSITIVITY.json
with the full grid plus a single "robustness" verdict:

    ROBUST   — every cell's break-even within ±10% of the canonical
    SENSITIVE — any cell drifts >25% from canonical
    MIXED    — between the two bands

Used to falsify the null hypothesis that the canonical gate value
(f* = 0.232 at q=0.75, window=300s) is an overfit of hyperparameters.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from research.microstructure.diurnal import session_start_ms_from_frames
from research.microstructure.diurnal_filter import (
    direction_per_row,
    load_hourly_direction_map,
)
from research.microstructure.killtest import cross_sectional_ricci_signal
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)
from research.microstructure.pnl import (
    DEFAULT_DECISION_SEC,
    DEFAULT_HOLD_SEC,
    DEFAULT_MAKER_FRACTIONS,
    DEFAULT_MEDIAN_WINDOW_SEC,
    CostModel,
    breakeven_maker_fraction,
    simulate_gross_trades,
    sweep_maker_fractions,
)
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)

_log = logging.getLogger("l2_ablation")

CANONICAL_BREAKEVEN: Final[float] = 0.23166569020507446
ROBUST_REL_TOLERANCE: Final[float] = 0.10
SENSITIVE_REL_TOLERANCE: Final[float] = 0.25


@dataclass(frozen=True)
class AblationCell:
    regime_quantile: float
    regime_window_sec: int
    breakeven_maker_fraction: float | None
    bracketed: bool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_ABLATION_SENSITIVITY.json"))
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--diurnal-ic-gate", type=float, default=0.03)
    parser.add_argument("--diurnal-p-gate", type=float, default=0.05)
    parser.add_argument(
        "--regime-quantiles",
        default="0.70,0.75,0.80",
        help="comma-separated quantile grid",
    )
    parser.add_argument(
        "--regime-windows-sec",
        default="180,300,450",
        help="comma-separated window grid",
    )
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features
    frames = loaded.frames

    signal = cross_sectional_ricci_signal(features.ofi)
    decision_idx = np.arange(0, features.n_rows, DEFAULT_DECISION_SEC, dtype=np.int64)

    hourly_map = load_hourly_direction_map(
        Path(args.diurnal_filter),
        ic_gate=float(args.diurnal_ic_gate),
        pvalue_gate=float(args.diurnal_p_gate),
    )
    start_ms = session_start_ms_from_frames(frames)
    direction_override = direction_per_row(hourly_map, start_ms=start_ms, n_rows=features.n_rows)
    cost_model = CostModel()

    quantiles = [float(q) for q in str(args.regime_quantiles).split(",")]
    windows = [int(w) for w in str(args.regime_windows_sec).split(",")]

    cells: list[AblationCell] = []
    for q in quantiles:
        for window in windows:
            rv_score = rolling_rv_regime(features, window_rows=window)
            mask = regime_mask_from_quantile(rv_score, quantile=q)
            trades = simulate_gross_trades(
                signal,
                features.mid,
                decision_idx=decision_idx,
                hold_rows=DEFAULT_HOLD_SEC,
                median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
                regime_mask=mask,
                direction_override=direction_override,
                name=f"REGIME_Q{int(q * 100):02d}+DIURNAL",
            )
            rows = sweep_maker_fractions(
                trades,
                symbols=features.symbols,
                cost_model=cost_model,
                maker_fractions=DEFAULT_MAKER_FRACTIONS,
            )
            be = breakeven_maker_fraction(rows)
            cells.append(
                AblationCell(
                    regime_quantile=q,
                    regime_window_sec=window,
                    breakeven_maker_fraction=float(be) if be is not None else None,
                    bracketed=be is not None,
                )
            )
            _log.info(
                "q=%.2f window=%ds  break-even=%s",
                q,
                window,
                f"{be:.4f}" if be is not None else "NOT_BRACKETED",
            )

    bracketed_values = [c.breakeven_maker_fraction for c in cells if c.bracketed]
    if not bracketed_values:
        verdict = "NO_BRACKET_FOUND"
    else:
        bracketed_arr = np.asarray(bracketed_values, dtype=np.float64)
        max_rel_drift = float(
            np.max(np.abs(bracketed_arr - CANONICAL_BREAKEVEN) / CANONICAL_BREAKEVEN)
        )
        if max_rel_drift <= ROBUST_REL_TOLERANCE:
            verdict = "ROBUST"
        elif max_rel_drift <= SENSITIVE_REL_TOLERANCE:
            verdict = "MIXED"
        else:
            verdict = "SENSITIVE"

    payload: dict[str, Any] = {
        "canonical_breakeven": CANONICAL_BREAKEVEN,
        "robust_rel_tolerance": ROBUST_REL_TOLERANCE,
        "sensitive_rel_tolerance": SENSITIVE_REL_TOLERANCE,
        "n_cells": len(cells),
        "n_bracketed": len(bracketed_values),
        "verdict": verdict,
        "max_relative_drift": (
            float(
                np.max(
                    np.abs(np.asarray(bracketed_values, dtype=np.float64) - CANONICAL_BREAKEVEN)
                    / CANONICAL_BREAKEVEN
                )
            )
            if bracketed_values
            else None
        ),
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "ablation verdict: %s (%d/%d cells bracketed)", verdict, len(bracketed_values), len(cells)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
