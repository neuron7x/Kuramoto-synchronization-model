# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the FETE runtime integration utilities."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from core.strategies import (
    FETE,
    FETEBacktestEngine,
    FETEConfig,
    PaperTradingAccount,
    RiskGuard,
    YahooFinanceDataFetcher,
)
from domain.position import Position


def _stub_yahoo_download(
    symbol: str, start: datetime, end: datetime, progress: bool = False
) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=3, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.5, 103.0],
            "Low": [99.0, 100.0, 101.5],
            "Close": [100.5, 101.8, 102.2],
            "Volume": [10, 12, 14],
        },
        index=index,
    )


def test_yahoo_fetcher_returns_candles() -> None:
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 4)
    fetcher = YahooFinanceDataFetcher(downloader=_stub_yahoo_download)

    candles = fetcher.fetch("BTC-USD", start=start, end=end)

    assert len(candles) == 3
    assert candles[0].timestamp.date().isoformat() == "2024-01-01"
    assert candles[-1].close == 102.2


def test_paper_account_rebalance_and_cash_management() -> None:
    now = datetime.now()
    account = PaperTradingAccount(initial_cash=1_000.0, transaction_cost=0.0, slippage=0.0)
    equity = account.equity({"BTC": 100.0}, timestamp=now, record=False)
    assert equity == 1_000.0

    trade = account.rebalance_to_fraction(
        "BTC",
        0.5,
        reference_price=100.0,
        equity=equity,
        timestamp=now,
    )
    assert trade is not None
    assert account.cash < 1_000.0
    position = account.positions["BTC"]
    assert position.quantity == 5.0

    # Attempt to exceed available cash; the engine should cap the size.
    later = now + timedelta(minutes=1)
    account.rebalance_to_fraction(
        "BTC",
        1.5,
        reference_price=120.0,
        equity=account.equity({"BTC": 120.0}, timestamp=later, record=False),
        timestamp=later,
    )
    assert (
        account.positions["BTC"].quantity
        <= account.equity({"BTC": 120.0}, timestamp=later, record=False) / 120.0
    )


def test_risk_guard_stop_loss_and_circuit_breaker() -> None:
    now = datetime.now()
    guard = RiskGuard(
        max_position_fraction=0.5,
        max_daily_loss=0.05,
        max_drawdown=0.1,
        stop_loss_pct=0.05,
    )
    guard.reset(1_000.0, timestamp=now)

    ok, reason = guard.check_equity(900.0, timestamp=now)
    assert not ok
    assert reason == "daily_loss"
    assert guard.circuit_breaker_active

    position = Position(symbol="BTC", quantity=1.0, entry_price=100.0, current_price=100.0)
    triggered = guard.stop_loss_triggered(position, 94.0, timestamp=now)
    assert triggered
    assert guard.events[-1].code == "stop_loss"


def test_risk_guard_tracks_peak_drawdown() -> None:
    now = datetime.now()
    guard = RiskGuard(
        max_position_fraction=0.5,
        max_daily_loss=1.0,
        max_drawdown=1.0,
        stop_loss_pct=0.05,
    )
    guard.reset(10_000.0, timestamp=now)

    deep_dip_time = now + timedelta(minutes=1)
    guard.check_equity(8_000.0, timestamp=deep_dip_time)
    assert guard.current_drawdown == pytest.approx(0.2)
    assert guard.max_observed_drawdown == pytest.approx(0.2)

    recovery_time = deep_dip_time + timedelta(minutes=1)
    guard.check_equity(9_500.0, timestamp=recovery_time)
    assert guard.current_drawdown == pytest.approx(0.05)
    assert guard.max_observed_drawdown == pytest.approx(0.2)


def test_backtest_engine_generates_report() -> None:
    prices = np.array([100.0, 101.0, 100.5, 102.0, 103.5, 104.0], dtype=float)
    probs = np.linspace(0.45, 0.6, prices.size)
    fete = FETE(FETEConfig())
    account = PaperTradingAccount(initial_cash=5_000.0, transaction_cost=0.0, slippage=0.0)
    guard = RiskGuard(
        max_position_fraction=0.3,
        max_daily_loss=0.5,
        max_drawdown=0.5,
        stop_loss_pct=0.1,
    )
    engine = FETEBacktestEngine(fete, account, guard)

    report = engine.run(prices, probs, symbol="BTC-USD")

    assert report.final_equity > 0
    assert len(report.equity_curve) == prices.size
    assert report.num_trades > 0
    assert "brier" in report.audit
