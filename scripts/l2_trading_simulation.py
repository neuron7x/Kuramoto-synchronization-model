#!/usr/bin/env python3
"""Realistic trading simulation of the Ricci cross-sectional signal.

Converts IC into P&L with realistic taker-fee and spread cost, under
two strategies:

    A. BASKET_SIGN — at each decision time t (every `decision_sec`),
       go long an equally-weighted basket of 10 perps when κ_min(t)
       is above its rolling median, short otherwise. Hold `hold_sec`.
       This reflects the empirical fact that IC(κ, fwd_return) is
       positive for every symbol — the cross-sectional signal encodes
       a broad-market directional predictor.

    B. BASKET_SIGN_REGIME_GATED — identical to A but positions are
       opened only when the rolling_rv regime score is above its
       q75 threshold (calibrated on all prior substrate).

Cost model (realistic for Binance USDT-M perps):
    * Taker fee: 4 bps per side (0.04%).
    * Effective half-spread cost: 0.5 bp for BTC/ETH, 1 bp for others.
      (Symmetric market-taking mid + half-spread on entry, mid - half-spread
      on exit, collapsed into a per-side bp charge.)
    * Funding: ignored (position held << 8h, funding epoch).

Metrics reported per strategy:
    * n_trades, win_rate, mean_return_bp, median_return_bp,
      gross_pnl_bp, net_pnl_bp, sharpe_per_trade, sharpe_annualized
      (assuming 24/7 trading, decision_sec intervals).
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

_TAKER_FEE_BP: float = 4.0  # per side
_HALF_SPREAD_BP_BTC_ETH: float = 0.5
_HALF_SPREAD_BP_OTHER: float = 1.0
_DECISION_SEC: int = 180
_HOLD_SEC: int = 180  # equals forward horizon used elsewhere
_MEDIAN_WINDOW_SEC: int = 3600  # 1h rolling median for signal direction
_RV_WINDOW_ROWS: int = 300


@dataclass
class StrategyResult:
    name: str
    n_trades: int
    n_gated_out: int
    win_rate: float
    mean_return_gross_bp: float
    mean_return_net_bp: float
    median_return_net_bp: float
    gross_pnl_bp: float
    net_pnl_bp: float
    cost_per_trade_bp: float
    sharpe_per_trade: float
    sharpe_annualized_24_7: float


def _spread_cost_bp(symbol: str) -> float:
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        return _HALF_SPREAD_BP_BTC_ETH
    return _HALF_SPREAD_BP_OTHER


def _round_trip_cost_bp(symbols: tuple[str, ...]) -> float:
    """Average round-trip cost per dollar notional in basis points."""
    half_spread_avg = float(np.mean([_spread_cost_bp(s) for s in symbols]))
    # entry + exit = 2 × taker fee + 2 × half-spread
    return 2.0 * _TAKER_FEE_BP + 2.0 * half_spread_avg


def _simulate(
    signal_1d: np.ndarray,
    mid: np.ndarray,
    *,
    decision_idx: np.ndarray,
    hold_rows: int,
    median_window_rows: int,
    regime_mask: np.ndarray | None,
    cost_bp: float,
) -> tuple[list[float], int]:
    """Return per-trade net bp returns (after cost) and count of gated-out trades.

    At each decision index i:
        * position_sign = +1 if signal_1d[i] > rolling_median(signal) else -1
        * if regime_mask is not None and regime_mask[i] is False → skip trade
        * realized_ret_per_symbol = log(mid[i+hold]) - log(mid[i])
        * gross_trade_bp = sign * mean_across_symbols(realized_ret) * 1e4
        * net_trade_bp  = gross_trade_bp - cost_bp
    """
    # Rolling median of the 1d Ricci signal
    n_rows = signal_1d.shape[0]
    rolling_median = np.full(n_rows, np.nan, dtype=np.float64)
    w = median_window_rows
    for t in range(w, n_rows):
        block = signal_1d[t - w : t]
        finite = block[np.isfinite(block)]
        if finite.size >= 50:
            rolling_median[t] = float(np.median(finite))

    trades: list[float] = []
    gated_out = 0
    log_mid = np.log(mid)
    for i in decision_idx:
        if i + hold_rows >= log_mid.shape[0]:
            break
        sig_now = float(signal_1d[i])
        med = float(rolling_median[i])
        if not np.isfinite(sig_now) or not np.isfinite(med):
            continue
        if regime_mask is not None and not bool(regime_mask[i]):
            gated_out += 1
            continue
        sign = 1.0 if sig_now > med else -1.0
        realized = (log_mid[i + hold_rows] - log_mid[i]).mean()
        gross_bp = sign * float(realized) * 1.0e4
        net_bp = gross_bp - cost_bp
        trades.append(net_bp)
    return trades, gated_out


def _strategy_result(
    name: str,
    trades: list[float],
    gated_out: int,
    cost_bp: float,
    decisions_total: int,
) -> StrategyResult:
    arr = np.array(trades, dtype=np.float64)
    if arr.size == 0:
        return StrategyResult(
            name=name,
            n_trades=0,
            n_gated_out=gated_out,
            win_rate=float("nan"),
            mean_return_gross_bp=float("nan"),
            mean_return_net_bp=float("nan"),
            median_return_net_bp=float("nan"),
            gross_pnl_bp=float("nan"),
            net_pnl_bp=float("nan"),
            cost_per_trade_bp=cost_bp,
            sharpe_per_trade=float("nan"),
            sharpe_annualized_24_7=float("nan"),
        )
    mean_net = float(arr.mean())
    std_net = float(arr.std(ddof=1)) if arr.size > 1 else float("nan")
    gross_arr = arr + cost_bp
    sr_per_trade = mean_net / std_net if std_net and std_net > 0 else float("nan")
    # Annualized: assume trades spaced `decision_sec`; 24/7 → 365.25 days
    trades_per_year = 365.25 * 24 * 3600 / float(_DECISION_SEC)
    sr_annualized = sr_per_trade * np.sqrt(trades_per_year)
    return StrategyResult(
        name=name,
        n_trades=int(arr.size),
        n_gated_out=gated_out,
        win_rate=float((arr > 0).mean()),
        mean_return_gross_bp=float(gross_arr.mean()),
        mean_return_net_bp=mean_net,
        median_return_net_bp=float(np.median(arr)),
        gross_pnl_bp=float(gross_arr.sum()),
        net_pnl_bp=float(arr.sum()),
        cost_per_trade_bp=cost_bp,
        sharpe_per_trade=sr_per_trade,
        sharpe_annualized_24_7=sr_annualized if np.isfinite(sr_annualized) else float("nan"),
    )


def main() -> int:
    data_dir = Path("data/binance_l2_perp")
    frames = load_parquets(data_dir, DEFAULT_SYMBOLS)
    features = build_feature_frame(frames, DEFAULT_SYMBOLS)
    print(f"substrate: n_rows={features.n_rows}  n_symbols={features.n_symbols}")

    signal = cross_sectional_ricci_signal(features.ofi)
    cost_bp = _round_trip_cost_bp(features.symbols)
    print(
        f"\ncost model: 2*({_TAKER_FEE_BP}bp taker) + 2*half_spread → {cost_bp:.2f} bp per round trip"
    )
    print(f"decision_sec={_DECISION_SEC}  hold_sec={_HOLD_SEC}")

    decision_idx = np.arange(0, features.n_rows, _DECISION_SEC, dtype=np.int64)

    # Strategy A: unconditional
    trades_A, gated_A = _simulate(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=_HOLD_SEC,
        median_window_rows=_MEDIAN_WINDOW_SEC,
        regime_mask=None,
        cost_bp=cost_bp,
    )
    result_A = _strategy_result(
        "BASKET_SIGN_UNCONDITIONAL", trades_A, gated_A, cost_bp, decision_idx.size
    )

    # Strategy B: regime-gated
    rv_score = rolling_rv_regime(features, window_rows=_RV_WINDOW_ROWS)
    mask_q75 = regime_mask_from_quantile(rv_score, quantile=0.75)
    trades_B, gated_B = _simulate(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=_HOLD_SEC,
        median_window_rows=_MEDIAN_WINDOW_SEC,
        regime_mask=mask_q75,
        cost_bp=cost_bp,
    )
    result_B = _strategy_result(
        "BASKET_SIGN_REGIME_Q75", trades_B, gated_B, cost_bp, decision_idx.size
    )

    for r in (result_A, result_B):
        print()
        print(f"=== {r.name} ===")
        print(f"  n_trades            = {r.n_trades}")
        print(f"  n_gated_out         = {r.n_gated_out}")
        print(f"  win_rate            = {r.win_rate:.3f}")
        print(f"  mean_gross_bp       = {r.mean_return_gross_bp:+.2f}")
        print(f"  cost_per_trade_bp   = {r.cost_per_trade_bp:+.2f}")
        print(f"  mean_net_bp         = {r.mean_return_net_bp:+.2f}")
        print(f"  median_net_bp       = {r.median_return_net_bp:+.2f}")
        print(f"  cumulative_net_bp   = {r.net_pnl_bp:+.1f}")
        print(f"  sharpe_per_trade    = {r.sharpe_per_trade:+.3f}")
        print(f"  sharpe_ann_24/7     = {r.sharpe_annualized_24_7:+.2f}")

    Path("results").mkdir(exist_ok=True)
    Path("results/L2_TRADING_SIMULATION.json").write_text(
        json.dumps(
            {
                "cost_bp_per_round_trip": cost_bp,
                "decision_sec": _DECISION_SEC,
                "hold_sec": _HOLD_SEC,
                "median_window_sec": _MEDIAN_WINDOW_SEC,
                "results": [asdict(result_A), asdict(result_B)],
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    print("\nwrote results/L2_TRADING_SIMULATION.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
