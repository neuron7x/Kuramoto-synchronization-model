#!/usr/bin/env python3
"""Slippage stress test for the REGIME_Q75+DIURNAL strategy.

The canonical cost model assumes half-spread ≈ 0.5 bp (BTC/ETH) or
1.0 bp (other) plus 4 bp taker fee / -2 bp maker rebate. Real execution
adds latency-driven slippage beyond the posted spread.

This sweep bumps half-spread by Δ_bp ∈ {0, 1, 2, 3, 5} on every symbol
and re-runs the maker-fraction sweep. Each bp of Δ adds 2 bp to RTC.

Verdict taxonomy:
    RESILIENT  — every stress level still viable (bracket below 0.50
                 OR already profitable at f=0)
    BOUND      — viability holds up to some Δ then collapses
    FRAGILE    — canonical Δ=0 is barely viable; small Δ collapses

Writes results/L2_SLIPPAGE_STRESS.json.
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

_log = logging.getLogger("l2_slippage_stress")

CANONICAL_HALF_SPREAD_BTC_ETH: Final[float] = 0.5
CANONICAL_HALF_SPREAD_OTHER: Final[float] = 1.0


@dataclass(frozen=True)
class StressCell:
    slippage_bp: float
    total_rtc_at_f0_bp: float  # round-trip cost at f=0 for this stress level
    breakeven_maker_fraction: float | None
    bracketed: bool
    profitable_at_f0: bool
    mean_net_bp_at_f0: float
    n_trades: int
    status: str  # BRACKET | ALREADY_PROFITABLE | UNVIABLE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_SLIPPAGE_STRESS.json"))
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--diurnal-ic-gate", type=float, default=0.03)
    parser.add_argument("--diurnal-p-gate", type=float, default=0.05)
    parser.add_argument(
        "--slippage-bp",
        default="0,1,2,3,5",
        help="comma-separated per-side slippage grid in bp",
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

    trades = simulate_gross_trades(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=DEFAULT_HOLD_SEC,
        median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
        regime_mask=mask,
        direction_override=direction_override,
        name="REGIME_Q75+DIURNAL",
    )

    slippages = [float(s) for s in str(args.slippage_bp).split(",")]

    cells: list[StressCell] = []
    for slip in slippages:
        cost_model = CostModel(
            taker_fee_bp=4.0,
            maker_rebate_bp=-2.0,
            half_spread_btc_eth_bp=CANONICAL_HALF_SPREAD_BTC_ETH + slip,
            half_spread_other_bp=CANONICAL_HALF_SPREAD_OTHER + slip,
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
        rtc_f0 = float(f0_row.round_trip_cost_bp) if f0_row is not None else float("nan")
        profitable_at_f0 = mean_f0 > 0.0
        if be is not None:
            status = "BRACKET"
        elif profitable_at_f0:
            status = "ALREADY_PROFITABLE"
        else:
            status = "UNVIABLE"
        cells.append(
            StressCell(
                slippage_bp=slip,
                total_rtc_at_f0_bp=rtc_f0,
                breakeven_maker_fraction=float(be) if be is not None else None,
                bracketed=be is not None,
                profitable_at_f0=profitable_at_f0,
                mean_net_bp_at_f0=mean_f0,
                n_trades=int(len(trades.gross_bp)),
                status=status,
            )
        )
        _log.info(
            "slippage=+%.1fbp  status=%-18s  f*=%s  mean_f0=%+.4f bp  RTC(f0)=%.2f bp",
            slip,
            status,
            f"{be:.4f}" if be is not None else "–",
            mean_f0,
            rtc_f0,
        )

    # Verdict: RESILIENT if all cells viable; BOUND if some but not all; FRAGILE if even 0 slippage fails.
    viable_statuses = {"BRACKET", "ALREADY_PROFITABLE"}
    baseline_viable = any(c.slippage_bp == 0.0 and c.status in viable_statuses for c in cells)
    all_viable = all(c.status in viable_statuses for c in cells)
    if not baseline_viable:
        verdict = "FRAGILE"
    elif all_viable:
        verdict = "RESILIENT"
    else:
        verdict = "BOUND"

    last_viable_slippage = max(
        (c.slippage_bp for c in cells if c.status in viable_statuses),
        default=float("-inf"),
    )

    payload: dict[str, Any] = {
        "regime_quantile": float(args.regime_quantile),
        "regime_window_sec": int(args.regime_window_sec),
        "hold_sec": int(DEFAULT_HOLD_SEC),
        "n_cells": len(cells),
        "max_slippage_still_viable_bp": float(last_viable_slippage),
        "verdict": verdict,
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "slippage stress verdict: %s  (max viable +%.1f bp / side)",
        verdict,
        last_viable_slippage,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
