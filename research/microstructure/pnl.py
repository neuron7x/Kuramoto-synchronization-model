"""Economic P&L evaluation of the L2 Ricci cross-sectional signal.

First-class module promoted from the former diagnostic scripts
`l2_trading_simulation.py` + `l2_execution_cost_sweep.py`.

Separation of concerns:
    cost model    — symbol-aware round-trip cost in bp, maker/taker mix
    gross P&L     — per-trade bp returns before cost (signal × realized)
    net P&L       — gross minus round-trip cost
    stats         — win-rate, Sharpe, cumulative, annualized
    break-even    — linear-interpolated maker fraction where mean net = 0
    sweep         — stats across a maker-fraction grid

Zero numerical logic change vs. the two source scripts — only packaging,
typing, and testability improvements. Fixture
`results/gate_fixtures/breakeven_q75.json` pins the REGIME_Q75 break-even
at 0.4072 ± 1e-3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
from numpy.typing import NDArray

DEFAULT_DECISION_SEC: Final[int] = 180
DEFAULT_HOLD_SEC: Final[int] = 180
DEFAULT_MEDIAN_WINDOW_SEC: Final[int] = 3600
DEFAULT_MAKER_FRACTIONS: Final[tuple[float, ...]] = (
    0.0,
    0.25,
    0.50,
    0.70,
    0.80,
    0.90,
    1.00,
)


@dataclass(frozen=True)
class CostModel:
    """Binance USDT-M perp cost model, bp-denominated."""

    taker_fee_bp: float = 4.0
    maker_rebate_bp: float = -2.0
    half_spread_btc_eth_bp: float = 0.5
    half_spread_other_bp: float = 1.0

    def half_spread_for(self, symbol: str) -> float:
        if symbol in {"BTCUSDT", "ETHUSDT"}:
            return self.half_spread_btc_eth_bp
        return self.half_spread_other_bp

    def round_trip_cost_bp(
        self,
        symbols: tuple[str, ...],
        *,
        maker_fraction: float = 0.0,
    ) -> float:
        """Average round-trip cost in bp for a basket, at given maker-fill fraction."""
        if not 0.0 <= maker_fraction <= 1.0:
            raise ValueError(f"maker_fraction must lie in [0, 1], got {maker_fraction}")
        half_spread_avg = float(np.mean([self.half_spread_for(s) for s in symbols]))
        taker_side = self.taker_fee_bp + half_spread_avg
        maker_side = self.maker_rebate_bp + half_spread_avg
        blended_side = maker_fraction * maker_side + (1.0 - maker_fraction) * taker_side
        return 2.0 * blended_side


@dataclass(frozen=True)
class StrategyStats:
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


@dataclass(frozen=True)
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


@dataclass
class GrossTrades:
    """Container for per-trade gross bp returns and simulation metadata."""

    name: str
    gross_bp: list[float] = field(default_factory=list)
    n_gated_out: int = 0


def simulate_gross_trades(
    signal_1d: NDArray[np.float64],
    mid_panel: NDArray[np.float64],
    *,
    decision_idx: NDArray[np.int64],
    hold_rows: int,
    median_window_rows: int,
    regime_mask: NDArray[np.bool_] | None = None,
    direction_override: NDArray[np.int64] | None = None,
    name: str = "BASKET_SIGN",
) -> GrossTrades:
    """Basket-sign strategy, pre-cost.

    Default rule (no direction_override):
        At each decision index i:
            * position_sign = +1 if signal_1d[i] > rolling_median(signal) else -1

    With direction_override (shape (n_rows,), values in {-1, 0, +1}):
        * position_sign = direction_override[i]
        * if direction_override[i] == 0 → skip as gated-out

    Common filters (both apply before direction is resolved):
        * if regime_mask[i] is False → skip (gated-out)
        * if signal or median non-finite → skip
        * realized_ret_per_symbol = log(mid[i+hold]) - log(mid[i])
        * gross_bp = sign * mean_across_symbols(realized_ret) * 1e4
    """
    n_rows = int(signal_1d.shape[0])
    if direction_override is not None and direction_override.shape != (n_rows,):
        raise ValueError(
            f"direction_override shape {direction_override.shape} must equal ({n_rows},)"
        )

    rolling_median = np.full(n_rows, np.nan, dtype=np.float64)
    w = median_window_rows
    for t in range(w, n_rows):
        block = signal_1d[t - w : t]
        finite = block[np.isfinite(block)]
        if finite.size >= 50:
            rolling_median[t] = float(np.median(finite))

    gross: list[float] = []
    gated = 0
    log_mid = np.log(mid_panel)
    for raw_i in decision_idx.tolist():
        i = int(raw_i)
        if i + hold_rows >= log_mid.shape[0]:
            break
        sig_now = float(signal_1d[i])
        med = float(rolling_median[i])
        if not np.isfinite(sig_now) or not np.isfinite(med):
            continue
        if regime_mask is not None and not bool(regime_mask[i]):
            gated += 1
            continue
        if direction_override is not None:
            override = int(direction_override[i])
            if override == 0:
                gated += 1
                continue
            sign = float(override)
        else:
            sign = 1.0 if sig_now > med else -1.0
        realized = float((log_mid[i + hold_rows] - log_mid[i]).mean())
        gross.append(sign * realized * 1.0e4)
    return GrossTrades(name=name, gross_bp=gross, n_gated_out=gated)


def compute_strategy_stats(
    trades: GrossTrades,
    *,
    cost_bp: float,
    decision_sec: int = DEFAULT_DECISION_SEC,
) -> StrategyStats:
    arr = np.array(trades.gross_bp, dtype=np.float64) - cost_bp
    if arr.size == 0:
        return StrategyStats(
            name=trades.name,
            n_trades=0,
            n_gated_out=trades.n_gated_out,
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
    sr = mean_net / std_net if std_net and std_net > 0 else float("nan")
    trades_per_year = 365.25 * 24 * 3600 / float(decision_sec)
    sr_ann = sr * float(np.sqrt(trades_per_year)) if np.isfinite(sr) else float("nan")
    return StrategyStats(
        name=trades.name,
        n_trades=int(arr.size),
        n_gated_out=trades.n_gated_out,
        win_rate=float((arr > 0).mean()),
        mean_return_gross_bp=float(gross_arr.mean()),
        mean_return_net_bp=mean_net,
        median_return_net_bp=float(np.median(arr)),
        gross_pnl_bp=float(gross_arr.sum()),
        net_pnl_bp=float(arr.sum()),
        cost_per_trade_bp=cost_bp,
        sharpe_per_trade=sr,
        sharpe_annualized_24_7=sr_ann if np.isfinite(sr_ann) else float("nan"),
    )


def sweep_maker_fractions(
    trades: GrossTrades,
    *,
    symbols: tuple[str, ...],
    cost_model: CostModel,
    maker_fractions: tuple[float, ...] = DEFAULT_MAKER_FRACTIONS,
    decision_sec: int = DEFAULT_DECISION_SEC,
) -> list[SweepRow]:
    rows: list[SweepRow] = []
    for mf in maker_fractions:
        rtc = cost_model.round_trip_cost_bp(symbols, maker_fraction=mf)
        stats = compute_strategy_stats(trades, cost_bp=rtc, decision_sec=decision_sec)
        rows.append(
            SweepRow(
                strategy=trades.name,
                maker_fraction=float(mf),
                round_trip_cost_bp=float(rtc),
                n_trades=stats.n_trades,
                win_rate=stats.win_rate,
                mean_net_bp=stats.mean_return_net_bp,
                cumulative_net_bp=stats.net_pnl_bp,
                sharpe_per_trade=stats.sharpe_per_trade,
                sharpe_annualized=stats.sharpe_annualized_24_7,
            )
        )
    return rows


def breakeven_maker_fraction(rows: list[SweepRow]) -> float | None:
    """Linear-interpolated maker fraction where mean_net_bp crosses zero.

    Expects rows sorted-or-sortable by maker_fraction. Returns None if no
    sign change is bracketed in the grid.
    """
    if not rows:
        return None
    s = sorted(rows, key=lambda r: r.maker_fraction)
    for a, b in zip(s, s[1:], strict=False):
        if a.mean_net_bp <= 0.0 <= b.mean_net_bp:
            if b.mean_net_bp == a.mean_net_bp:
                return float(a.maker_fraction)
            t = (0.0 - a.mean_net_bp) / (b.mean_net_bp - a.mean_net_bp)
            return float(a.maker_fraction + t * (b.maker_fraction - a.maker_fraction))
    return None
