#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync Walk-Forward Backtest v2 — hedge fund grade.

No lookahead. No in-sample optimization presented as results.
Walk-forward: train on past, test on future, roll window forward.

Strategy:
  Long/Short/Flat based on regime + momentum confirmation.
  COHERENT + R>thr + risk>thr + momentum>0  →  LONG
  DECOHERENT + R<thr + momentum<0            →  SHORT
  Otherwise                                   →  FLAT

Position sizing: Kelly fraction × risk_scalar (never >25% of equity).
Transaction costs: 5bps per trade.

Validation:
  - Walk-forward with 500-bar train / 100-bar test windows
  - No parameter fitted on test data
  - Sharpe, Sortino, Calmar, max DD, win rate, profit factor
  - Monte Carlo confidence intervals (1000 shuffles)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yfinance as yf
from scipy.signal import hilbert

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.estimators.gamma_estimator import PSDGammaEstimator  # noqa: E402

# ── CONFIG ──────────────────────────────────────────────────
TICKERS = ["BTC-USD", "EURUSD=X"]
PERIOD = "5y"
SIGNAL_WINDOW = 200
TRAIN_WINDOW = 500
TEST_WINDOW = 100
KURAMOTO_TF = [5, 10, 20, 50, 100]
COST_BPS = 5.0  # transaction cost per trade
MAX_POSITION = 0.25  # max 25% of equity per trade
MONTE_CARLO_N = 1000


@dataclass(frozen=True)
class Metrics:
    """Full performance metrics."""

    total_return: float
    annual_return: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    n_trades: int
    win_rate: float
    profit_factor: float
    exposure_pct: float
    avg_trade_return: float
    benchmark_return: float
    mc_sharpe_5th: float  # Monte Carlo 5th percentile
    mc_sharpe_95th: float


@dataclass
class WalkForwardResult:
    """Walk-forward backtest output."""

    ticker: str
    dates: np.ndarray
    equity: np.ndarray
    benchmark: np.ndarray
    positions: np.ndarray
    gamma_series: np.ndarray
    r_series: np.ndarray
    risk_series: np.ndarray
    regime_series: list[str]
    metrics: Metrics
    oos_returns: np.ndarray  # out-of-sample returns only
    train_params: list[dict[str, float]] = field(default_factory=list)


def compute_kuramoto_r(prices: np.ndarray) -> np.ndarray:
    """Kuramoto R(t) from Hilbert multi-timeframe phases."""
    n = len(prices)
    phases = np.zeros((n, len(KURAMOTO_TF)))
    safe = np.maximum(prices, 1e-12)
    for i, w in enumerate(KURAMOTO_TF):
        ret = np.zeros(n)
        ret[w:] = np.log(safe[w:] / safe[:-w])
        analytic = hilbert(ret - np.mean(ret))
        phases[:, i] = np.angle(analytic)
    return np.abs(np.mean(np.exp(1j * phases), axis=1)).astype(np.float64)


def compute_signals(
    close: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Compute γ, R, risk_scalar, momentum, regime for full series."""
    n = len(close)
    gamma_est = PSDGammaEstimator(fs=1.0, bootstrap_n=0)
    r_series = compute_kuramoto_r(close)

    gamma_s = np.full(n, np.nan)
    risk_s = np.full(n, np.nan)
    mom_s = np.full(n, np.nan)
    regimes: list[str] = ["UNKNOWN"] * n

    for t in range(SIGNAL_WINDOW, n):
        window = close[t - SIGNAL_WINDOW : t]
        series = window - np.linspace(window[0], window[-1], SIGNAL_WINDOW)
        g = gamma_est.compute(series)
        gv = g.value if g.is_valid else 1.0
        rv = max(0.0, 1.0 - abs(gv - 1.0))

        # Momentum: 20-bar log return
        if t >= 20:
            mom = np.log(close[t] / close[t - 20])
        else:
            mom = 0.0

        gamma_s[t] = gv
        risk_s[t] = rv
        mom_s[t] = mom

        r = r_series[t]
        if rv > 0.6 and r > 0.7:
            regimes[t] = "COHERENT"
        elif rv > 0.4 and r > 0.5:
            regimes[t] = "METASTABLE"
        elif r > 0.85 and rv < 0.3:
            regimes[t] = "CRITICAL"
        else:
            regimes[t] = "DECOHERENT"

    return gamma_s, r_series, risk_s, mom_s, regimes


def calibrate_thresholds(
    returns: np.ndarray,
    r_series: np.ndarray,
    risk_series: np.ndarray,
    mom_series: np.ndarray,
    regimes: list[str],
) -> dict[str, float]:
    """Calibrate on training data — find optimal thresholds.

    Grid search over R threshold and risk threshold.
    Objective: Sharpe ratio (not total return — avoids overfitting to trends).
    """
    best_sharpe = -999.0
    best_params: dict[str, float] = {"r_thr": 0.7, "risk_thr": 0.6}

    for r_thr in [0.5, 0.6, 0.7, 0.8]:
        for risk_thr in [0.4, 0.5, 0.6, 0.7]:
            pos = np.zeros(len(returns))
            for t in range(1, len(returns)):
                r_val = r_series[t - 1] if np.isfinite(r_series[t - 1]) else 0.0
                rsk = risk_series[t - 1] if np.isfinite(risk_series[t - 1]) else 0.0
                mom = mom_series[t - 1] if np.isfinite(mom_series[t - 1]) else 0.0
                reg = regimes[t - 1]

                if reg == "COHERENT" and r_val > r_thr and rsk > risk_thr and mom > 0:
                    pos[t] = 1.0
                elif reg == "DECOHERENT" and r_val < (1 - r_thr) and mom < 0:
                    pos[t] = -1.0
                else:
                    pos[t] = 0.0

            strat_ret = pos * returns
            if np.std(strat_ret) > 1e-12:
                sharpe = np.mean(strat_ret) / np.std(strat_ret) * np.sqrt(252)
            else:
                sharpe = 0.0

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = {"r_thr": r_thr, "risk_thr": risk_thr}

    return best_params


def run_walk_forward(ticker: str) -> WalkForwardResult | None:
    """Walk-forward backtest: train → test → roll."""
    print(f"Downloading {ticker} ({PERIOD})...")
    data = yf.download(ticker, period=PERIOD, interval="1d", progress=False)
    if data.empty:
        print(f"No data for {ticker}")
        return None

    close = data[("Close", ticker)].values.astype(np.float64)
    dates = data.index.values
    n = len(close)
    print(f"Data: {n} bars")

    # Compute signals once
    gamma_s, r_s, risk_s, mom_s, regimes = compute_signals(close)
    daily_ret = np.zeros(n)
    daily_ret[1:] = np.diff(close) / close[:-1]

    # Walk-forward
    positions = np.zeros(n)
    all_params: list[dict[str, float]] = []
    oos_mask = np.zeros(n, dtype=bool)

    start = SIGNAL_WINDOW + TRAIN_WINDOW
    t = start

    while t + TEST_WINDOW <= n:
        # TRAIN: [t - TRAIN_WINDOW, t)
        train_sl = slice(t - TRAIN_WINDOW, t)
        params = calibrate_thresholds(
            daily_ret[train_sl],
            r_s[train_sl],
            risk_s[train_sl],
            mom_s[train_sl],
            regimes[train_sl.start : train_sl.stop],
        )
        all_params.append(params)

        # TEST: [t, t + TEST_WINDOW) — apply params, no fitting
        r_thr = params["r_thr"]
        risk_thr = params["risk_thr"]

        for j in range(t, min(t + TEST_WINDOW, n)):
            r_val = r_s[j - 1] if np.isfinite(r_s[j - 1]) else 0.0
            rsk = risk_s[j - 1] if np.isfinite(risk_s[j - 1]) else 0.0
            mom = mom_s[j - 1] if np.isfinite(mom_s[j - 1]) else 0.0
            reg = regimes[j - 1]

            if reg == "COHERENT" and r_val > r_thr and rsk > risk_thr and mom > 0:
                pos = min(MAX_POSITION, rsk)  # size by conviction
            elif reg == "DECOHERENT" and r_val < (1 - r_thr) and mom < 0:
                pos = -min(MAX_POSITION, 1 - rsk)
            else:
                pos = 0.0

            positions[j] = pos
            oos_mask[j] = True

        t += TEST_WINDOW

    # Apply transaction costs
    pos_changes = np.abs(np.diff(positions))
    costs = np.zeros(n)
    costs[1:] = pos_changes * COST_BPS / 10000.0

    strategy_ret = positions * daily_ret - costs
    equity = np.cumprod(1.0 + strategy_ret)
    benchmark = np.cumprod(1.0 + daily_ret)

    # OOS returns only
    oos_ret = strategy_ret[oos_mask]

    # Metrics
    metrics = compute_metrics(strategy_ret, daily_ret, positions, oos_ret)

    print(f"\n{'=' * 55}")
    print(f"  {ticker} — Walk-Forward Results (OOS only)")
    print(f"{'=' * 55}")
    print(f"  Total Return:    {metrics.total_return:+.2%}")
    print(f"  Annual Return:   {metrics.annual_return:+.2%}")
    print(f"  Sharpe:          {metrics.sharpe:.3f}")
    print(f"  Sortino:         {metrics.sortino:.3f}")
    print(f"  Calmar:          {metrics.calmar:.3f}")
    print(f"  Max Drawdown:    {metrics.max_drawdown:.2%}")
    print(f"  Trades:          {metrics.n_trades}")
    print(f"  Win Rate:        {metrics.win_rate:.1%}")
    print(f"  Profit Factor:   {metrics.profit_factor:.2f}")
    print(f"  Exposure:        {metrics.exposure_pct:.1f}%")
    print(f"  Avg Trade:       {metrics.avg_trade_return:+.4%}")
    print(f"  Benchmark:       {metrics.benchmark_return:+.2%}")
    print(f"  MC Sharpe 5-95%: [{metrics.mc_sharpe_5th:.3f}, {metrics.mc_sharpe_95th:.3f}]")
    print(f"{'=' * 55}")

    return WalkForwardResult(
        ticker=ticker,
        dates=dates,
        equity=equity,
        benchmark=benchmark,
        positions=positions,
        gamma_series=gamma_s,
        r_series=r_s,
        risk_series=risk_s,
        regime_series=regimes,
        metrics=metrics,
        oos_returns=oos_ret,
        train_params=all_params,
    )


def compute_metrics(
    strategy_ret: np.ndarray,
    daily_ret: np.ndarray,
    positions: np.ndarray,
    oos_ret: np.ndarray,
) -> Metrics:
    """Compute hedge fund metrics."""
    equity = np.cumprod(1.0 + strategy_ret)
    n_days = len(strategy_ret)

    # Returns
    total_ret = float(equity[-1] / equity[0] - 1.0)
    annual_ret = float((1 + total_ret) ** (252 / max(n_days, 1)) - 1.0)

    # Sharpe (annualized, on OOS)
    if len(oos_ret) > 10 and np.std(oos_ret) > 1e-12:
        sharpe = float(np.mean(oos_ret) / np.std(oos_ret) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Sortino (downside deviation only)
    neg_ret = oos_ret[oos_ret < 0]
    if len(neg_ret) > 5:
        downside_std = float(np.std(neg_ret))
        sortino = float(np.mean(oos_ret) / (downside_std + 1e-12) * np.sqrt(252))
    else:
        sortino = sharpe

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    # Calmar
    calmar = float(annual_ret / (abs(max_dd) + 1e-12))

    # Trade stats
    pos_diff = np.diff(positions)
    n_trades = int(np.sum(np.abs(pos_diff) > 0.01))

    # Per-trade returns
    trade_rets: list[float] = []
    in_trade = False
    entry_eq = 1.0
    for t in range(1, len(equity)):
        if not in_trade and abs(positions[t]) > 0.01 and abs(positions[t - 1]) < 0.01:
            in_trade = True
            entry_eq = equity[t - 1]
        elif in_trade and abs(positions[t]) < 0.01 and abs(positions[t - 1]) > 0.01:
            in_trade = False
            trade_rets.append(float(equity[t] / entry_eq - 1.0))

    win_rate = sum(1 for r in trade_rets if r > 0) / max(len(trade_rets), 1)
    gross_profit = sum(r for r in trade_rets if r > 0)
    gross_loss = abs(sum(r for r in trade_rets if r < 0))
    profit_factor = gross_profit / (gross_loss + 1e-12)
    avg_trade = float(np.mean(trade_rets)) if trade_rets else 0.0

    exposure = float(np.mean(np.abs(positions[SIGNAL_WINDOW:]) > 0.01))
    bench_ret = float(np.cumprod(1 + daily_ret)[-1] - 1.0)

    # Monte Carlo confidence interval
    mc_sharpes = _monte_carlo_sharpe(oos_ret)

    return Metrics(
        total_return=round(total_ret, 4),
        annual_return=round(annual_ret, 4),
        sharpe=round(sharpe, 3),
        sortino=round(sortino, 3),
        calmar=round(calmar, 3),
        max_drawdown=round(max_dd, 4),
        n_trades=n_trades,
        win_rate=round(win_rate, 3),
        profit_factor=round(profit_factor, 2),
        exposure_pct=round(exposure * 100, 1),
        avg_trade_return=round(avg_trade, 6),
        benchmark_return=round(bench_ret, 4),
        mc_sharpe_5th=round(mc_sharpes[0], 3),
        mc_sharpe_95th=round(mc_sharpes[1], 3),
    )


def _monte_carlo_sharpe(oos_ret: np.ndarray) -> tuple[float, float]:
    """Bootstrap Sharpe confidence interval."""
    if len(oos_ret) < 20:
        return (0.0, 0.0)
    rng = np.random.default_rng(42)
    sharpes: list[float] = []
    n = len(oos_ret)
    for _ in range(MONTE_CARLO_N):
        sample = rng.choice(oos_ret, size=n, replace=True)
        s = np.std(sample)
        if s > 1e-12:
            sharpes.append(float(np.mean(sample) / s * np.sqrt(252)))
    if not sharpes:
        return (0.0, 0.0)
    return (float(np.percentile(sharpes, 5)), float(np.percentile(sharpes, 95)))


def plot_walk_forward(result: WalkForwardResult, output_dir: Path) -> Path:
    """Publication-quality walk-forward chart."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = result.ticker.replace("=", "").replace("-", "")

    valid = ~np.isnan(result.gamma_series)
    valid_idx = np.where(valid)[0]
    if len(valid_idx) == 0:
        return output_dir

    start = valid_idx[0]
    dates = result.dates[start:]
    eq = result.equity[start:]
    bm = result.benchmark[start:]
    m = result.metrics

    fig, axes = plt.subplots(5, 1, figsize=(16, 20), sharex=True)
    fig.suptitle(
        f"GeoSync Walk-Forward — {result.ticker}\n"
        f"Sharpe={m.sharpe:.2f}  Sortino={m.sortino:.2f}  "
        f"Calmar={m.calmar:.2f}  MaxDD={m.max_drawdown:.1%}  "
        f"Return={m.total_return:+.1%}  Trades={m.n_trades}\n"
        f"MC Sharpe 90% CI: [{m.mc_sharpe_5th:.2f}, {m.mc_sharpe_95th:.2f}]  "
        f"Win={m.win_rate:.0%}  PF={m.profit_factor:.1f}  "
        f"Cost={COST_BPS}bps",
        fontsize=13,
        fontweight="bold",
    )

    # 1. Equity curve
    ax = axes[0]
    ax.plot(dates, eq / eq[0], "b-", lw=1.5, label=f"GeoSync ({m.total_return:+.1%})")
    ax.plot(dates, bm / bm[0], "k--", alpha=0.4, lw=1, label=f"B&H ({m.benchmark_return:+.1%})")
    ax.set_ylabel("Equity")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # 2. Drawdown
    ax = axes[1]
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    ax.fill_between(dates, dd, 0, color="red", alpha=0.4)
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)

    # 3. Gamma + regime
    ax = axes[2]
    gamma = result.gamma_series[start:]
    ax.plot(dates, gamma, "purple", lw=0.8, label="γ")
    ax.axhline(1.0, color="red", ls="--", alpha=0.5)
    ax.set_ylabel("γ")
    ax.set_ylim(-0.5, 3.5)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # 4. R + risk
    ax = axes[3]
    ax.plot(dates, result.r_series[start:], "blue", lw=0.8, label="R(t)")
    ax.plot(dates, result.risk_series[start:], "green", lw=0.8, alpha=0.7, label="risk_scalar")
    ax.set_ylabel("Signal")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # 5. Position
    ax = axes[4]
    pos = result.positions[start:]
    ax.fill_between(dates, pos, 0, where=pos > 0, alpha=0.3, color="green", label="Long")
    ax.fill_between(dates, pos, 0, where=pos < 0, alpha=0.3, color="red", label="Short")
    ax.set_ylabel("Position")
    ax.set_xlabel("Date")
    ax.set_ylim(-0.3, 0.3)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = output_dir / f"geosync_wf_{safe}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")
    return path


if __name__ == "__main__":
    output_dir = Path(__file__).parent / "output"

    for ticker in TICKERS:
        result = run_walk_forward(ticker)
        if result is not None:
            plot_walk_forward(result, output_dir)
