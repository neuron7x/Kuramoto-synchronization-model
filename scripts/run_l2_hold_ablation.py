#!/usr/bin/env python3
"""Hold-time ablation for the REGIME_Q75+DIURNAL strategy.

Sweeps the execution horizon (hold_sec) across {60, 90, 180, 300, 600}
keeping all other hyperparameters canonical. For each horizon, runs the
full maker-fraction sweep and records the break-even point.

Answers: is the canonical 180-s hold-time specifically tuned, or does
the edge survive across trading horizons?

Verdict taxonomy:
    ROBUST   — every horizon brackets break-even below 0.50
    MIXED    — most but not all bracket under 0.50
    COLLAPSING — break-even exceeds 0.50 or not bracketed for ≥1 horizon

Writes results/L2_HOLD_ABLATION.json.
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

_log = logging.getLogger("l2_hold_ablation")

ROBUST_MAX_BREAKEVEN: Final[float] = 0.50
CANONICAL_HOLD_SEC: Final[int] = 180


@dataclass(frozen=True)
class HoldCell:
    hold_sec: int
    breakeven_maker_fraction: float | None
    bracketed: bool
    profitable_at_f0: bool
    mean_net_bp_at_f0: float
    n_trades: int
    status: str  # BRACKET | ALREADY_PROFITABLE | UNVIABLE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_HOLD_ABLATION.json"))
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--diurnal-ic-gate", type=float, default=0.03)
    parser.add_argument("--diurnal-p-gate", type=float, default=0.05)
    parser.add_argument(
        "--hold-sec",
        default="60,90,180,300,600",
        help="comma-separated hold-time grid in seconds",
    )
    parser.add_argument("--regime-quantile", type=float, default=0.75)
    parser.add_argument("--regime-window-sec", type=int, default=300)
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

    rv_score = rolling_rv_regime(features, window_rows=int(args.regime_window_sec))
    mask = regime_mask_from_quantile(rv_score, quantile=float(args.regime_quantile))

    hourly_map = load_hourly_direction_map(
        Path(args.diurnal_filter),
        ic_gate=float(args.diurnal_ic_gate),
        pvalue_gate=float(args.diurnal_p_gate),
    )
    start_ms = session_start_ms_from_frames(frames)
    direction_override = direction_per_row(hourly_map, start_ms=start_ms, n_rows=features.n_rows)

    cost_model = CostModel()
    hold_secs = [int(h) for h in str(args.hold_sec).split(",")]

    cells: list[HoldCell] = []
    for hold in hold_secs:
        trades = simulate_gross_trades(
            signal,
            features.mid,
            decision_idx=decision_idx,
            hold_rows=hold,
            median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
            regime_mask=mask,
            direction_override=direction_override,
            name=f"REGIME_Q75+DIURNAL@{hold}s",
        )
        rows = sweep_maker_fractions(
            trades,
            symbols=features.symbols,
            cost_model=cost_model,
            maker_fractions=DEFAULT_MAKER_FRACTIONS,
        )
        be = breakeven_maker_fraction(rows)
        f0_row = next((r for r in rows if r.maker_fraction == 0.0), None)
        mean_f0 = float(f0_row.mean_net_bp) if f0_row is not None else float("nan")
        profitable_at_f0 = mean_f0 > 0.0
        if be is not None:
            status = "BRACKET"
        elif profitable_at_f0:
            status = "ALREADY_PROFITABLE"
        else:
            status = "UNVIABLE"
        cells.append(
            HoldCell(
                hold_sec=hold,
                breakeven_maker_fraction=float(be) if be is not None else None,
                bracketed=be is not None,
                profitable_at_f0=profitable_at_f0,
                mean_net_bp_at_f0=mean_f0,
                n_trades=int(len(trades.gross_bp)),
                status=status,
            )
        )
        _log.info(
            "hold=%3ds  status=%-18s  f*=%s  mean_f0=%+.4f bp  n_trades=%d",
            hold,
            status,
            f"{be:.4f}" if be is not None else "–",
            mean_f0,
            len(trades.gross_bp),
        )

    # "Viable" = bracketed with f* ≤ 0.50, OR already profitable at f=0.
    viable = [c for c in cells if c.status in {"BRACKET", "ALREADY_PROFITABLE"}]
    bracketed = [c for c in cells if c.status == "BRACKET"]
    already = [c for c in cells if c.status == "ALREADY_PROFITABLE"]
    max_breakeven = (
        max(c.breakeven_maker_fraction for c in bracketed if c.breakeven_maker_fraction is not None)
        if bracketed
        else 0.0
    )
    all_viable = len(viable) == len(cells)

    if all_viable and (not bracketed or max_breakeven <= ROBUST_MAX_BREAKEVEN):
        verdict = "ROBUST"
    elif all_viable:
        verdict = "MIXED"
    else:
        verdict = "COLLAPSING"

    payload: dict[str, Any] = {
        "canonical_hold_sec": CANONICAL_HOLD_SEC,
        "robust_max_breakeven": ROBUST_MAX_BREAKEVEN,
        "regime_quantile": float(args.regime_quantile),
        "regime_window_sec": int(args.regime_window_sec),
        "n_cells": len(cells),
        "n_bracketed": len(bracketed),
        "n_already_profitable": len(already),
        "n_viable": len(viable),
        "max_breakeven": float(max_breakeven),
        "verdict": verdict,
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "hold-ablation verdict: %s  (%d/%d bracketed, max f*=%.4f)",
        verdict,
        len(bracketed),
        len(cells),
        max_breakeven,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
