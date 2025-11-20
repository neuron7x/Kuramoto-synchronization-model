# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for portfolio PnL accounting utilities."""

from __future__ import annotations

import pytest

from domain import OrderSide
from execution.portfolio import PortfolioAccounting


def test_apply_fill_and_realised_pnl() -> None:
    accounting = PortfolioAccounting(initial_cash=10_000.0)

    accounting.apply_fill(
        "BTCUSDT", OrderSide.BUY, quantity=1.0, price=1_000.0, fees=5.0
    )
    assert pytest.approx(accounting.realized_pnl(), rel=1e-9) == 0.0
    assert pytest.approx(accounting.positions()["BTCUSDT"].quantity, rel=1e-9) == 1.0
    assert (
        pytest.approx(accounting.positions()["BTCUSDT"].entry_price, rel=1e-9)
        == 1_000.0
    )
    assert pytest.approx(accounting.snapshot().cash, rel=1e-9) == 8_995.0

    accounting.mark_to_market("BTCUSDT", 1_100.0)
    assert pytest.approx(accounting.unrealized_pnl(), rel=1e-9) == 100.0

    accounting.apply_fill(
        "BTCUSDT", OrderSide.SELL, quantity=1.0, price=1_100.0, fees=5.0
    )
    assert pytest.approx(accounting.realized_pnl(), rel=1e-9) == 100.0
    assert pytest.approx(accounting.unrealized_pnl(), rel=1e-9) == 0.0
    assert "BTCUSDT" in accounting.positions()
    assert pytest.approx(accounting.positions()["BTCUSDT"].quantity, rel=1e-9) == 0.0


def test_snapshot_aggregates_metrics() -> None:
    accounting = PortfolioAccounting(initial_cash=5_000.0)
    accounting.apply_fill("ETHUSDT", OrderSide.BUY, quantity=2.0, price=500.0)
    accounting.mark_to_market("ETHUSDT", 550.0)

    snapshot = accounting.snapshot()

    assert snapshot.cash == pytest.approx(4_000.0)
    assert snapshot.realized_pnl == pytest.approx(0.0)
    assert snapshot.unrealized_pnl == pytest.approx(100.0)
    assert snapshot.gross_exposure == pytest.approx(1_100.0)
    assert snapshot.net_exposure == pytest.approx(1_100.0)
    assert snapshot.equity == pytest.approx(5_100.0)
