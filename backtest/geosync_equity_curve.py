#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync physics-driven backtest — equity curve from real market data.

Strategy:
  COHERENT regime + R(t) > 0.7 + risk_scalar > 0.6  →  LONG
  DECOHERENT regime  →  FLAT
  Otherwise  →  hold previous position

Physics signals (rolling 200-bar window):
  γ  — PSD spectral exponent (Welch)
  R(t) — Kuramoto order parameter (Hilbert multi-timeframe phases)
  risk_scalar = max(0, 1 - |γ - 1|)
  regime = f(γ, R)

Data: Yahoo Finance daily OHLC, no registration required.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yfinance as yf
from scipy.signal import hilbert

# Add project root to path for geosync imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.estimators.gamma_estimator import PSDGammaEstimator  # noqa: E402

# ── CONFIG ──────────────────────────────────────────────────
TICKER = "BTC-USD"
TICKERS_ALL = ["BTC-USD", "EURUSD=X"]
PERIOD = "5y"
WINDOW = 200  # rolling window for signal computation
R_THRESHOLD = 0.7
RISK_THRESHOLD = 0.6
KURAMOTO_TIMEFRAMES = [5, 10, 20, 50, 100]


@dataclass
class BacktestResult:
    """Full backtest output."""

    dates: np.ndarray
    equity: np.ndarray
    benchmark: np.ndarray
    positions: np.ndarray
    gamma_series: np.ndarray
    r_series: np.ndarray
    risk_series: np.ndarray
    regime_series: list[str]
    sharpe: float
    max_drawdown: float
    total_return: float
    benchmark_return: float
    n_trades: int
    win_rate: float
    exposure_pct: float


def classify_regime(gamma: float, r_val: float) -> str:
    """Classify market regime from γ and R(t).

    COHERENT:    γ near 1.0 (critical) + high synchrony
    METASTABLE:  γ near 1.0 but low synchrony
    DECOHERENT:  γ far from 1.0 (random or trending)
    CRITICAL:    very high R + γ diverging (herding)
    """
    risk = max(0.0, 1.0 - abs(gamma - 1.0))

    if risk > 0.6 and r_val > 0.7:
        return "COHERENT"
    if risk > 0.4 and r_val > 0.5:
        return "METASTABLE"
    if r_val > 0.85 and risk < 0.3:
        return "CRITICAL"
    return "DECOHERENT"


def compute_kuramoto_r(prices: np.ndarray, timeframes: list[int]) -> np.ndarray:
    """Kuramoto R(t) from Hilbert-transformed multi-timeframe returns."""
    n = len(prices)
    phases = np.zeros((n, len(timeframes)))

    for i, w in enumerate(timeframes):
        ret = np.zeros(n)
        safe_prices = np.maximum(prices, 1e-12)
        ret[w:] = np.log(safe_prices[w:] / safe_prices[:-w])
        centered = ret - np.mean(ret)
        analytic = hilbert(centered)
        phases[:, i] = np.angle(analytic)

    return np.abs(np.mean(np.exp(1j * phases), axis=1)).astype(np.float64)


def run_backtest(ticker: str = TICKER) -> BacktestResult | None:
    """Execute full backtest."""
    # ── DATA ────────────────────────────────────────────────
    print(f"Downloading {ticker} ({PERIOD})...")
    data = yf.download(ticker, period=PERIOD, interval="1d", progress=False)
    if data.empty:
        print(f"ERROR: no data for {ticker} — skipping")
        return None
    close = data[("Close", ticker)].values.astype(np.float64)
    dates = data.index.values

    n = len(close)
    print(f"Data: {n} bars, {dates[0]} to {dates[-1]}")

    # ── SIGNALS ─────────────────────────────────────────────
    gamma_est = PSDGammaEstimator(fs=1.0, bootstrap_n=0)
    r_series = compute_kuramoto_r(close, KURAMOTO_TIMEFRAMES)

    gamma_series = np.full(n, np.nan)
    risk_series = np.full(n, np.nan)
    regime_series: list[str] = ["UNKNOWN"] * n

    print("Computing signals...")
    for t in range(WINDOW, n):
        window_data = close[t - WINDOW : t]
        # Use detrended price (not returns) for PSD — captures scaling structure
        series = window_data - np.linspace(window_data[0], window_data[-1], WINDOW)

        g = gamma_est.compute(series)
        gamma_val = g.value if g.is_valid else 1.0
        risk_val = max(0.0, 1.0 - abs(gamma_val - 1.0))
        regime = classify_regime(gamma_val, r_series[t])

        gamma_series[t] = gamma_val
        risk_series[t] = risk_val
        regime_series[t] = regime

    # ── TRADING LOGIC ───────────────────────────────────────
    # COHERENT + R > 0.7 + risk > 0.6 → long
    # DECOHERENT → flat
    # Otherwise → hold
    positions = np.zeros(n)
    daily_returns = np.zeros(n)
    daily_returns[1:] = np.diff(close) / close[:-1]

    pos = 0.0
    for t in range(WINDOW + 1, n):
        regime = regime_series[t - 1]  # signal from previous bar
        r_val = r_series[t - 1]
        risk_val = risk_series[t - 1] if np.isfinite(risk_series[t - 1]) else 0.0

        if regime == "COHERENT" and r_val > R_THRESHOLD and risk_val > RISK_THRESHOLD:
            pos = 1.0
        elif regime == "DECOHERENT":
            pos = 0.0
        # else: hold previous

        positions[t] = pos

    # ── EQUITY CURVE ────────────────────────────────────────
    strategy_returns = positions * daily_returns
    equity = np.cumprod(1.0 + strategy_returns)
    benchmark = np.cumprod(1.0 + daily_returns)

    # ── METRICS ─────────────────────────────────────────────
    # Sharpe (annualized)
    sr = strategy_returns[WINDOW:]
    sharpe = np.mean(sr) / (np.std(sr) + 1e-12) * np.sqrt(252)

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    # Trade counting
    pos_diff = np.diff(positions)
    n_trades = int(np.sum(pos_diff > 0))

    # Win rate (per trade)
    trade_returns: list[float] = []
    in_trade = False
    entry_equity = 1.0
    for t in range(1, n):
        if not in_trade and positions[t] > 0 and positions[t - 1] == 0:
            in_trade = True
            entry_equity = equity[t - 1]
        elif in_trade and positions[t] == 0 and positions[t - 1] > 0:
            in_trade = False
            trade_returns.append(equity[t] / entry_equity - 1.0)

    win_rate = sum(1 for r in trade_returns if r > 0) / max(len(trade_returns), 1)

    total_return = float(equity[-1] / equity[0] - 1.0)
    bench_return = float(benchmark[-1] / benchmark[0] - 1.0)
    exposure = float(np.mean(positions[WINDOW:] > 0))

    result = BacktestResult(
        dates=dates,
        equity=equity,
        benchmark=benchmark,
        positions=positions,
        gamma_series=gamma_series,
        r_series=r_series,
        risk_series=risk_series,
        regime_series=regime_series,
        sharpe=round(sharpe, 3),
        max_drawdown=round(max_dd, 4),
        total_return=round(total_return, 4),
        benchmark_return=round(bench_return, 4),
        n_trades=n_trades,
        win_rate=round(win_rate, 3),
        exposure_pct=round(exposure * 100, 1),
    )

    print(f"\n{'=' * 50}")
    print(f"GeoSync Backtest — {TICKER} ({PERIOD})")
    print(f"{'=' * 50}")
    print(f"Total Return:     {result.total_return:+.2%}")
    print(f"Benchmark:        {result.benchmark_return:+.2%}")
    print(f"Sharpe Ratio:     {result.sharpe:.3f}")
    print(f"Max Drawdown:     {result.max_drawdown:.2%}")
    print(f"Trades:           {result.n_trades}")
    print(f"Win Rate:         {result.win_rate:.1%}")
    print(f"Exposure:         {result.exposure_pct:.1f}%")
    print(f"{'=' * 50}")

    return result


def plot_results(result: BacktestResult, output_dir: Path) -> list[Path]:
    """Generate publication-quality charts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    valid = ~np.isnan(result.gamma_series)
    valid_idx = np.where(valid)[0]
    if len(valid_idx) == 0:
        print("No valid signals to plot")
        return files

    start = valid_idx[0]
    dates = result.dates[start:]
    equity = result.equity[start:]
    benchmark = result.benchmark[start:]

    # ── 1. Equity Curve ────────────────────────────────────
    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)
    fig.suptitle(
        f"GeoSync Physics Backtest — {TICKER}\n"
        f"Sharpe={result.sharpe:.2f}  MaxDD={result.max_drawdown:.2%}  "
        f"Return={result.total_return:+.2%}  Trades={result.n_trades}",
        fontsize=14,
        fontweight="bold",
    )

    # Panel 1: Equity vs benchmark
    ax = axes[0]
    ax.plot(dates, equity / equity[0], "b-", linewidth=1.5, label="GeoSync Strategy")
    ax.plot(dates, benchmark / benchmark[0], "k--", alpha=0.5, linewidth=1, label="Buy & Hold")
    ax.set_ylabel("Equity (normalized)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # Panel 2: γ and regime
    ax = axes[1]
    gamma = result.gamma_series[start:]
    ax.plot(dates, gamma, "purple", linewidth=0.8, label="γ (PSD)")
    ax.axhline(1.0, color="red", linestyle="--", alpha=0.5, label="γ=1 (critical)")
    ax.set_ylabel("γ")
    ax.set_ylim(-0.5, 3.5)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # Color background by regime
    regime_colors = {
        "COHERENT": "#2ecc71",
        "METASTABLE": "#f39c12",
        "DECOHERENT": "#e74c3c",
        "CRITICAL": "#9b59b6",
    }
    regimes = result.regime_series[start:]
    prev_regime = regimes[0]
    block_start = 0
    for i in range(1, len(regimes)):
        if regimes[i] != prev_regime or i == len(regimes) - 1:
            color = regime_colors.get(prev_regime, "#cccccc")
            ax.axvspan(dates[block_start], dates[i], alpha=0.1, color=color)
            block_start = i
            prev_regime = regimes[i]

    # Panel 3: R(t) and risk_scalar
    ax = axes[2]
    r = result.r_series[start:]
    risk = result.risk_series[start:]
    ax.plot(dates, r, "blue", linewidth=0.8, label="R(t) Kuramoto")
    ax.plot(dates, risk, "green", linewidth=0.8, alpha=0.7, label="risk_scalar")
    ax.axhline(R_THRESHOLD, color="blue", linestyle=":", alpha=0.5)
    ax.axhline(RISK_THRESHOLD, color="green", linestyle=":", alpha=0.5)
    ax.set_ylabel("Signal")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # Panel 4: Position
    ax = axes[3]
    pos = result.positions[start:]
    ax.fill_between(dates, pos, 0, alpha=0.3, color="blue", label="Position (1=long)")
    ax.set_ylabel("Position")
    ax.set_xlabel("Date")
    ax.set_ylim(-0.1, 1.1)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = output_dir / "geosync_equity_curve.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    files.append(path)
    print(f"Saved: {path}")

    # ── 2. Drawdown chart ──────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 4))
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    ax.fill_between(dates, dd, 0, color="red", alpha=0.4)
    ax.set_title("Drawdown")
    ax.set_ylabel("Drawdown %")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = output_dir / "geosync_drawdown.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    files.append(path)
    print(f"Saved: {path}")

    return files


def plot_results_for_ticker(ticker: str, result: BacktestResult, output_dir: Path) -> list[Path]:
    """Plot with ticker-specific filenames."""
    safe = ticker.replace("=", "").replace("-", "")
    files: list[Path] = []

    valid = ~np.isnan(result.gamma_series)
    valid_idx = np.where(valid)[0]
    if len(valid_idx) == 0:
        return files

    start = valid_idx[0]
    dates = result.dates[start:]
    equity = result.equity[start:]
    benchmark = result.benchmark[start:]

    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)
    fig.suptitle(
        f"GeoSync Physics Backtest — {ticker}\n"
        f"Sharpe={result.sharpe:.2f}  MaxDD={result.max_drawdown:.2%}  "
        f"Return={result.total_return:+.2%}  Trades={result.n_trades}",
        fontsize=14,
        fontweight="bold",
    )

    ax = axes[0]
    ax.plot(dates, equity / equity[0], "b-", linewidth=1.5, label="GeoSync Strategy")
    ax.plot(dates, benchmark / benchmark[0], "k--", alpha=0.5, linewidth=1, label="Buy & Hold")
    ax.set_ylabel("Equity (normalized)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(dates, result.gamma_series[start:], "purple", linewidth=0.8, label="γ (PSD)")
    ax.axhline(1.0, color="red", linestyle="--", alpha=0.5, label="γ=1 (critical)")
    ax.set_ylabel("γ")
    ax.set_ylim(-0.5, 3.5)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(dates, result.r_series[start:], "blue", linewidth=0.8, label="R(t) Kuramoto")
    ax.plot(
        dates, result.risk_series[start:], "green", linewidth=0.8, alpha=0.7, label="risk_scalar"
    )
    ax.axhline(R_THRESHOLD, color="blue", linestyle=":", alpha=0.5)
    ax.axhline(RISK_THRESHOLD, color="green", linestyle=":", alpha=0.5)
    ax.set_ylabel("Signal")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    ax.fill_between(dates, result.positions[start:], 0, alpha=0.3, color="blue", label="Position")
    ax.set_ylabel("Position")
    ax.set_xlabel("Date")
    ax.set_ylim(-0.1, 1.1)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = output_dir / f"geosync_{safe}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    files.append(path)
    print(f"Saved: {path}")
    return files


if __name__ == "__main__":
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    for tk in TICKERS_ALL:
        print(f"\n{'=' * 60}")
        print(f"  {tk}")
        print(f"{'=' * 60}")
        result = run_backtest(tk)
        if result is None:
            continue
        plot_results_for_ticker(tk, result, output_dir)
        plot_results(result, output_dir)
