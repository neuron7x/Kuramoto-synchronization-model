#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Live backtest — GeoSync Kuramoto+Ricci on real EURUSD 1h data.

Uses GeoSyncCompositeEngine for regime detection and
EventDrivenBacktestEngine for realistic execution with costs.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Result  # noqa: E402
from backtest.event_driven import EventDrivenBacktestEngine  # noqa: E402
from core.indicators.kuramoto_ricci_composite import (  # noqa: E402
    GeoSyncCompositeEngine,
)

WINDOW = 200
INITIAL_CAPITAL = 100_000.0
TICKERS = ["EURUSD=X", "BTC-USD"]


def _make_signal_fn(engine: GeoSyncCompositeEngine) -> object:
    """Signal function: prices array → signal array {0.0, 1.0}."""

    def fn(prices: np.ndarray) -> np.ndarray:
        n = len(prices)
        signal = np.zeros(n)
        for i in range(WINDOW, n):
            engine._clear_history()
            chunk = prices[i - WINDOW : i]
            df = pd.DataFrame(
                {"close": chunk, "volume": np.ones(WINDOW) * 1000.0},
                index=pd.date_range("2020-01-01", periods=WINDOW, freq="1h"),
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    snap = engine.analyze_market(df)
                except Exception:
                    signal[i] = 0.0
                    continue

            r = snap.kuramoto_R
            phase = snap.phase.value

            if r > 0.65 and snap.confidence > 0.5 and phase != "chaotic":
                signal[i] = 1.0
            elif phase in ("chaotic", "post_emergent") or r < 0.4:
                signal[i] = 0.0
            else:
                signal[i] = signal[i - 1]
        return signal

    return fn


def _download(ticker: str) -> np.ndarray | None:
    """Download prices, return Close array or None."""
    print(f"Downloading {ticker} 1h...")
    df = yf.download(ticker, period="2y", interval="1h", progress=False)
    if df.empty:
        print("  1h empty, trying daily 5y...")
        df = yf.download(ticker, period="5y", interval="1d", progress=False)
    if df.empty:
        print(f"  ERROR: no data for {ticker}")
        return None
    df = df.dropna()
    col = ("Close", ticker) if isinstance(df.columns, pd.MultiIndex) else "Close"
    prices = df[col].values.astype(np.float64)
    print(f"  {len(prices)} bars, {df.index[0]} → {df.index[-1]}")
    return prices


def _run_one(ticker: str) -> None:
    prices = _download(ticker)
    if prices is None:
        return

    engine = GeoSyncCompositeEngine()
    sig_fn = _make_signal_fn(engine)

    print(f"  Running backtest ({len(prices)} bars)...")
    bt = EventDrivenBacktestEngine()
    result: Result = bt.run(
        prices,
        sig_fn,
        initial_capital=INITIAL_CAPITAL,
        strategy_name=f"geosync_{ticker.replace('=', '').replace('-', '_').lower()}",
    )

    ret_pct = result.pnl / INITIAL_CAPITAL * 100

    print(f"\n{'=' * 50}")
    print(f"  {ticker} — GeoSync Live Backtest")
    print(f"{'=' * 50}")
    print(f"  P&L:          ${result.pnl:,.2f}")
    print(f"  Return:       {ret_pct:+.2f}%")
    print(f"  Max Drawdown: {result.max_dd:.2%}")
    print(f"  Trades:       {result.trades}")
    print(f"  Commission:   ${result.commission_cost:,.2f}")

    if result.performance and hasattr(result.performance, "sharpe"):
        print(f"  Sharpe:       {result.performance.sharpe:.3f}")

    print(f"{'=' * 50}")

    if result.equity_curve is not None:
        eq = pd.Series(result.equity_curve)
        safe = ticker.replace("=", "").replace("-", "")
        out = Path(__file__).parent / "output" / f"equity_curve_{safe}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        eq.to_csv(out)
        print(f"  Saved: {out}")
        print(f"  Peak:  ${eq.max():,.2f}  Final: ${eq.iloc[-1]:,.2f}")

        rets = eq.pct_change().dropna()
        if len(rets) > 10 and rets.std() > 1e-12:
            annual = 252 * 24 if len(prices) > 5000 else 252
            sh = float(rets.mean() / rets.std() * np.sqrt(annual))
            print(f"  Annualized Sharpe: {sh:.3f}")


if __name__ == "__main__":
    for t in TICKERS:
        _run_one(t)
