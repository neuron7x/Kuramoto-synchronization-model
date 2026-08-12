#!/usr/bin/env python3
"""Sweep execution cost regimes: at what maker-fill-rate does the signal pay?

Runs the same basket-sign strategy as `l2_trading_simulation.py` but
evaluates it under a continuum of cost models, parameterised by
`maker_fill_fraction` ∈ [0, 1]. At 0 we pay full taker costs; at 1 we
are pure maker (rebate + half-spread).

Cost model per side:
    taker: +4 bp fee + half-spread bp
    maker: -2 bp rebate + half-spread bp
    blended = maker_fraction × maker_cost + (1 − maker_fraction) × taker_cost

Round-trip cost = 2 × blended (entry + exit).

Emits: per maker_fraction, net P&L stats (mean, Sharpe per trade).
Identifies the break-even fraction for the q75 regime-gated strategy.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)

_TAKER_FEE_BP: float = 4.0
_MAKER_REBATE_BP: float = -2.0  # negative = rebate paid to us
_HALF_SPREAD_BP_BTC_ETH: float = 0.5
_HALF_SPREAD_BP_OTHER: float = 1.0
_DECISION_SEC: int = 180
_HOLD_SEC: int = 180
_MEDIAN_WINDOW_SEC: int = 3600
_RV_WINDOW_ROWS: int = 300
_MAKER_FRACS: tuple[float, ...] = (0.0, 0.25, 0.50, 0.70, 0.80, 0.90, 1.00)


@dataclass
class SweepRow:
    strategy: str
    maker_fraction: float
    round_trip_cost_bp: float
    n_trades: int
    win_rate: float
    mean_net_bp: float
    cumulative_net_bp: float
    sharpe_per_trade: float
    sharpe_annualized: float


def _half_spread_avg(symbols: tuple[str, ...]) -> float:
    vals = [
        _HALF_SPREAD_BP_BTC_ETH if s in {"BTCUSDT", "ETHUSDT"} else _HALF_SPREAD_BP_OTHER
        for s in symbols
    ]
    return float(np.mean(vals))


def _round_trip_cost(maker_fraction: float, half_spread: float) -> float:
    taker_side = _TAKER_FEE_BP + half_spread
    maker_side = _MAKER_REBATE_BP + half_spread
    blended_side = maker_fraction * maker_side + (1.0 - maker_fraction) * taker_side
    return 2.0 * blended_side


def _simulate_gross(
    signal_1d: np.ndarray,
    mid: np.ndarray,
    *,
    decision_idx: np.ndarray,
    hold_rows: int,
    median_window_rows: int,
    regime_mask: np.ndarray | None,
) -> list[float]:
    """Per-trade gross bp return list (before costs)."""
    n_rows = signal_1d.shape[0]
    rolling_median = np.full(n_rows, np.nan, dtype=np.float64)
    w = median_window_rows
    for t in range(w, n_rows):
        block = signal_1d[t - w : t]
        finite = block[np.isfinite(block)]
        if finite.size >= 50:
            rolling_median[t] = float(np.median(finite))

    log_mid = np.log(mid)
    trades: list[float] = []
    for i in decision_idx:
        if i + hold_rows >= log_mid.shape[0]:
            break
        sig_now = float(signal_1d[i])
        med = float(rolling_median[i])
        if not np.isfinite(sig_now) or not np.isfinite(med):
            continue
        if regime_mask is not None and not bool(regime_mask[i]):
            continue
        sign = 1.0 if sig_now > med else -1.0
        realized = (log_mid[i + hold_rows] - log_mid[i]).mean()
        trades.append(sign * float(realized) * 1.0e4)
    return trades


def _finalize(
    strategy_name: str,
    gross_trades: list[float],
    maker_fraction: float,
    round_trip_cost_bp: float,
) -> SweepRow:
    if not gross_trades:
        return SweepRow(
            strategy=strategy_name,
            maker_fraction=maker_fraction,
            round_trip_cost_bp=round_trip_cost_bp,
            n_trades=0,
            win_rate=float("nan"),
            mean_net_bp=float("nan"),
            cumulative_net_bp=float("nan"),
            sharpe_per_trade=float("nan"),
            sharpe_annualized=float("nan"),
        )
    net = np.array(gross_trades, dtype=np.float64) - round_trip_cost_bp
    mean_net = float(net.mean())
    std_net = float(net.std(ddof=1)) if net.size > 1 else float("nan")
    sr = mean_net / std_net if std_net and std_net > 0 else float("nan")
    trades_per_year = 365.25 * 24 * 3600 / float(_DECISION_SEC)
    sr_ann = sr * float(np.sqrt(trades_per_year))
    return SweepRow(
        strategy=strategy_name,
        maker_fraction=maker_fraction,
        round_trip_cost_bp=round_trip_cost_bp,
        n_trades=int(net.size),
        win_rate=float((net > 0).mean()),
        mean_net_bp=mean_net,
        cumulative_net_bp=float(net.sum()),
        sharpe_per_trade=sr,
        sharpe_annualized=sr_ann if np.isfinite(sr_ann) else float("nan"),
    )


def main() -> int:
    data_dir = Path("data/binance_l2_perp")
    frames = load_parquets(data_dir, DEFAULT_SYMBOLS)
    features = build_feature_frame(frames, DEFAULT_SYMBOLS)
    print(f"substrate: n_rows={features.n_rows}  n_symbols={features.n_symbols}")
    signal = cross_sectional_ricci_signal(features.ofi)
    half_spread = _half_spread_avg(features.symbols)
    rv_score = rolling_rv_regime(features, window_rows=_RV_WINDOW_ROWS)
    mask_q75 = regime_mask_from_quantile(rv_score, quantile=0.75)
    decision_idx = np.arange(0, features.n_rows, _DECISION_SEC, dtype=np.int64)

    gross_un = _simulate_gross(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=_HOLD_SEC,
        median_window_rows=_MEDIAN_WINDOW_SEC,
        regime_mask=None,
    )
    gross_q75 = _simulate_gross(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=_HOLD_SEC,
        median_window_rows=_MEDIAN_WINDOW_SEC,
        regime_mask=mask_q75,
    )

    print(f"gross trade samples: uncond={len(gross_un)}  regime_q75={len(gross_q75)}")
    print(f"half-spread avg bp = {half_spread:.2f}\n")

    rows: list[SweepRow] = []
    for maker_frac in _MAKER_FRACS:
        rtc = _round_trip_cost(maker_frac, half_spread)
        rows.append(_finalize("UNCONDITIONAL", list(gross_un), maker_frac, rtc))
        rows.append(_finalize("REGIME_Q75", list(gross_q75), maker_frac, rtc))

    header = (
        f"{'strategy':<16} {'maker%':>7} {'rtc_bp':>7} {'n':>4} "
        f"{'win%':>5} {'mean_net':>8} {'SR_tr':>6} {'SR_ann':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r.strategy:<16} {r.maker_fraction * 100:>7.0f} {r.round_trip_cost_bp:>+7.2f} "
            f"{r.n_trades:>4} {r.win_rate * 100:>5.1f} {r.mean_net_bp:>+8.2f} "
            f"{r.sharpe_per_trade:>+6.3f} {r.sharpe_annualized:>+7.2f}"
        )

    # Identify break-even maker fraction per strategy (linear interpolation)
    def _breakeven(strategy: str) -> float | None:
        subset = [r for r in rows if r.strategy == strategy]
        for a, b in zip(subset, subset[1:], strict=False):
            if a.mean_net_bp <= 0.0 <= b.mean_net_bp:
                # linear interpolate
                if b.mean_net_bp == a.mean_net_bp:
                    return float(a.maker_fraction)
                t = (0.0 - a.mean_net_bp) / (b.mean_net_bp - a.mean_net_bp)
                return float(a.maker_fraction + t * (b.maker_fraction - a.maker_fraction))
        return None

    print("\n=== Break-even maker fraction (mean net = 0) ===")
    for s in ("UNCONDITIONAL", "REGIME_Q75"):
        be = _breakeven(s)
        if be is None:
            print(f"  {s:<20}  never reached in the sweep or always positive/negative")
        else:
            print(f"  {s:<20}  maker_fraction* = {be * 100:.1f} %")

    Path("results").mkdir(exist_ok=True)
    Path("results/L2_EXEC_COST_SWEEP.json").write_text(
        json.dumps([asdict(r) for r in rows], indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print("\nwrote results/L2_EXEC_COST_SWEEP.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
