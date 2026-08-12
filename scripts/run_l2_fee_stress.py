#!/usr/bin/env python3
"""Fee-sensitivity stress test for the REGIME_Q75+DIURNAL strategy.

Binance USDT-M perp taker fee is 4 bp canonical but varies by VIP tier
(2-5 bp depending on 30-day volume) and maker rebate can be -2 bp or
break-even. This sweep perturbs taker_fee ∈ {3, 4, 5, 6} bp with the
maker rebate fixed at −2 bp and records the break-even maker fraction.

Verdict taxonomy:
    RESILIENT — every tier viable (BRACKET below 0.50 OR
                ALREADY_PROFITABLE at f=0)
    BOUND     — viable up to a tier then collapses
    FRAGILE   — even canonical tier is marginal

Writes results/L2_FEE_STRESS.json.
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

_log = logging.getLogger("l2_fee_stress")

CANONICAL_TAKER_FEE_BP: Final[float] = 4.0


@dataclass(frozen=True)
class FeeCell:
    taker_fee_bp: float
    total_rtc_at_f0_bp: float
    breakeven_maker_fraction: float | None
    bracketed: bool
    profitable_at_f0: bool
    mean_net_bp_at_f0: float
    n_trades: int
    status: str  # BRACKET | ALREADY_PROFITABLE | UNVIABLE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_FEE_STRESS.json"))
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--diurnal-ic-gate", type=float, default=0.03)
    parser.add_argument("--diurnal-p-gate", type=float, default=0.05)
    parser.add_argument(
        "--taker-fees-bp",
        default="3,4,5,6",
        help="comma-separated taker-fee grid in bp",
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

    fees = [float(f) for f in str(args.taker_fees_bp).split(",")]

    cells: list[FeeCell] = []
    for fee in fees:
        cost_model = CostModel(taker_fee_bp=fee, maker_rebate_bp=-2.0)
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
            FeeCell(
                taker_fee_bp=fee,
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
            "taker=%.1f bp  status=%-18s  f*=%s  RTC(f0)=%.2f  mean_f0=%+.4f",
            fee,
            status,
            f"{be:.4f}" if be is not None else "–",
            rtc_f0,
            mean_f0,
        )

    viable_statuses = {"BRACKET", "ALREADY_PROFITABLE"}
    baseline_viable = any(
        c.taker_fee_bp == CANONICAL_TAKER_FEE_BP and c.status in viable_statuses for c in cells
    )
    all_viable = all(c.status in viable_statuses for c in cells)
    if not baseline_viable:
        verdict = "FRAGILE"
    elif all_viable:
        verdict = "RESILIENT"
    else:
        verdict = "BOUND"

    max_viable_fee = max(
        (c.taker_fee_bp for c in cells if c.status in viable_statuses),
        default=float("-inf"),
    )

    payload: dict[str, Any] = {
        "canonical_taker_fee_bp": CANONICAL_TAKER_FEE_BP,
        "regime_quantile": float(args.regime_quantile),
        "regime_window_sec": int(args.regime_window_sec),
        "hold_sec": int(DEFAULT_HOLD_SEC),
        "n_cells": len(cells),
        "max_viable_taker_fee_bp": float(max_viable_fee),
        "verdict": verdict,
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "fee stress verdict: %s  (max viable taker fee %.1f bp)",
        verdict,
        max_viable_fee,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
