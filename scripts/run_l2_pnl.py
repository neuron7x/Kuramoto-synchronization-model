#!/usr/bin/env python3
"""Economic P&L evaluation CLI over `research.microstructure.pnl`.

Modes:
    default         → strategy stats at taker-only cost
    --cost-sweep    → maker-fraction sweep + break-even maker
    --regime-filter → apply rv-q75 regime mask to strategy

Flags:
    --data-dir PATH                  substrate parquet dir (default data/binance_l2_perp)
    --symbols CSV                    override default symbol list
    --output PATH                    verdict JSON path
    --regime-filter                  enable rv-q75 regime mask
    --regime-quantile FLOAT          quantile for regime mask (default 0.75)
    --regime-window-sec INT          rolling window rows (default 300)
    --cost-sweep                     maker-fraction sweep mode
    --emit-gate-value {breakeven_q75}  minimal gate-JSON output

Exit: 0 on verdict produced, 2 on data / arg error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS
from research.microstructure.pnl import (
    DEFAULT_DECISION_SEC,
    DEFAULT_HOLD_SEC,
    DEFAULT_MAKER_FRACTIONS,
    DEFAULT_MEDIAN_WINDOW_SEC,
    CostModel,
    breakeven_maker_fraction,
    compute_strategy_stats,
    simulate_gross_trades,
    sweep_maker_fractions,
)
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)

_log = logging.getLogger("l2_pnl")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/binance_l2_perp"))
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/L2_TRADING_SIMULATION.json"),
    )
    parser.add_argument("--regime-filter", action="store_true")
    parser.add_argument("--regime-quantile", type=float, default=0.75)
    parser.add_argument("--regime-window-sec", type=int, default=300)
    parser.add_argument(
        "--diurnal-filter",
        type=Path,
        default=None,
        help="Path to L2_DIURNAL_PROFILE.json; enables per-row sign-aware filter",
    )
    parser.add_argument(
        "--diurnal-ic-gate",
        type=float,
        default=0.03,
        help="Min |hourly_IC| for diurnal direction (default 0.03)",
    )
    parser.add_argument(
        "--diurnal-p-gate",
        type=float,
        default=0.05,
        help="Max hourly permutation p for direction (default 0.05)",
    )
    parser.add_argument("--cost-sweep", action="store_true")
    parser.add_argument(
        "--emit-gate-value",
        choices=["breakeven_q75", "breakeven_q75_diurnal"],
        default=None,
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        _log.error("data dir does not exist: %s", data_dir)
        return 2

    frames = load_parquets(data_dir, symbols)
    if not frames:
        _log.error("no parquet shards in %s", data_dir)
        return 2

    try:
        features = build_feature_frame(frames, symbols)
    except ValueError as exc:
        _log.error("insufficient overlap: %s", exc)
        return 2

    signal = cross_sectional_ricci_signal(features.ofi)
    decision_idx = np.arange(0, features.n_rows, DEFAULT_DECISION_SEC, dtype=np.int64)

    strategy_name = "REGIME_Q75" if args.regime_filter else "UNCONDITIONAL"
    regime_mask = None
    if args.regime_filter:
        rv_score = rolling_rv_regime(features, window_rows=args.regime_window_sec)
        regime_mask = regime_mask_from_quantile(rv_score, quantile=args.regime_quantile)

    direction_override = None
    if args.diurnal_filter is not None:
        from research.microstructure.diurnal import session_start_ms_from_frames
        from research.microstructure.diurnal_filter import (
            direction_per_row,
            load_hourly_direction_map,
            summarize_map,
        )

        hourly_map = load_hourly_direction_map(
            Path(args.diurnal_filter),
            ic_gate=float(args.diurnal_ic_gate),
            pvalue_gate=float(args.diurnal_p_gate),
        )
        start_ms = session_start_ms_from_frames(frames)
        direction_override = direction_per_row(
            hourly_map, start_ms=start_ms, n_rows=features.n_rows
        )
        strategy_name = f"{strategy_name}+DIURNAL"
        _log.info("diurnal filter map: %s", summarize_map(hourly_map))
        _log.info(
            "diurnal rows with direction != 0: %d / %d",
            int(np.count_nonzero(direction_override)),
            features.n_rows,
        )

    trades = simulate_gross_trades(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=DEFAULT_HOLD_SEC,
        median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
        regime_mask=regime_mask,
        direction_override=direction_override,
        name=strategy_name,
    )

    cost_model = CostModel()

    if args.cost_sweep:
        # Run BOTH strategies in sweep mode so break-even applies to REGIME_Q75 regardless of --regime-filter
        rv_score_full = rolling_rv_regime(features, window_rows=args.regime_window_sec)
        mask_q75 = regime_mask_from_quantile(rv_score_full, quantile=args.regime_quantile)
        trades_uncond = simulate_gross_trades(
            signal,
            features.mid,
            decision_idx=decision_idx,
            hold_rows=DEFAULT_HOLD_SEC,
            median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
            regime_mask=None,
            name="UNCONDITIONAL",
        )
        trades_q75 = simulate_gross_trades(
            signal,
            features.mid,
            decision_idx=decision_idx,
            hold_rows=DEFAULT_HOLD_SEC,
            median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
            regime_mask=mask_q75,
            name="REGIME_Q75",
        )
        rows_uncond = sweep_maker_fractions(
            trades_uncond,
            symbols=features.symbols,
            cost_model=cost_model,
            maker_fractions=DEFAULT_MAKER_FRACTIONS,
        )
        rows_q75 = sweep_maker_fractions(
            trades_q75,
            symbols=features.symbols,
            cost_model=cost_model,
            maker_fractions=DEFAULT_MAKER_FRACTIONS,
        )
        be_uncond = breakeven_maker_fraction(rows_uncond)
        be_q75 = breakeven_maker_fraction(rows_q75)

        rows_q75_diurnal = None
        be_q75_diurnal = None
        if direction_override is not None:
            trades_q75_diurnal = simulate_gross_trades(
                signal,
                features.mid,
                decision_idx=decision_idx,
                hold_rows=DEFAULT_HOLD_SEC,
                median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
                regime_mask=mask_q75,
                direction_override=direction_override,
                name="REGIME_Q75+DIURNAL",
            )
            rows_q75_diurnal = sweep_maker_fractions(
                trades_q75_diurnal,
                symbols=features.symbols,
                cost_model=cost_model,
                maker_fractions=DEFAULT_MAKER_FRACTIONS,
            )
            be_q75_diurnal = breakeven_maker_fraction(rows_q75_diurnal)

        if args.emit_gate_value == "breakeven_q75":
            if be_q75 is None:
                _log.error("break-even maker fraction not bracketed in sweep")
                return 2
            print(
                json.dumps(
                    {
                        "gate": "breakeven_q75",
                        "value": float(be_q75),
                        "tolerance": 1.0e-3,
                    },
                    indent=2,
                )
            )
            return 0

        if args.emit_gate_value == "breakeven_q75_diurnal":
            if be_q75_diurnal is None:
                _log.error(
                    "breakeven_q75_diurnal requires --diurnal-filter and a "
                    "zero-crossing bracket; none found"
                )
                return 2
            print(
                json.dumps(
                    {
                        "gate": "breakeven_q75_diurnal",
                        "value": float(be_q75_diurnal),
                        "tolerance": 1.0e-3,
                    },
                    indent=2,
                )
            )
            return 0

        payload: dict[str, Any] = {
            "mode": "cost_sweep",
            "maker_fractions": list(DEFAULT_MAKER_FRACTIONS),
            "breakeven_uncond": be_uncond,
            "breakeven_regime_q75": be_q75,
            "breakeven_regime_q75_diurnal": be_q75_diurnal,
            "rows_uncond": [asdict(r) for r in rows_uncond],
            "rows_regime_q75": [asdict(r) for r in rows_q75],
            "rows_regime_q75_diurnal": (
                [asdict(r) for r in rows_q75_diurnal] if rows_q75_diurnal is not None else None
            ),
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0

    # Non-sweep mode: single strategy stats at taker-only cost
    rtc = cost_model.round_trip_cost_bp(features.symbols, maker_fraction=0.0)
    stats = compute_strategy_stats(trades, cost_bp=rtc)

    if args.emit_gate_value == "breakeven_q75":
        _log.error("--emit-gate-value breakeven_q75 requires --cost-sweep")
        return 2

    payload_simple: dict[str, Any] = {
        "mode": "single",
        "strategy": strategy_name,
        "symbols": list(features.symbols),
        "n_rows": features.n_rows,
        "stats": asdict(stats),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(payload_simple, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload_simple, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
