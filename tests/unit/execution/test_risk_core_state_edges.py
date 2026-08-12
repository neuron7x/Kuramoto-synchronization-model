# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Exposure-state edge tests for execution risk core."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from execution.risk import RiskLimits, RiskManager, portfolio_heat


class RecordingRiskStateStore:
    """In-memory risk-state store that records persisted exposure snapshots."""

    def __init__(
        self,
        *,
        positions: Mapping[str, float] | None = None,
        notionals: Mapping[str, float] | None = None,
    ) -> None:
        self._snapshot = (
            dict(positions or {}),
            dict(notionals or {}),
        )
        self.saved: list[tuple[dict[str, float], dict[str, float]]] = []

    def load(self) -> tuple[Mapping[str, float], Mapping[str, float]] | None:
        return self._snapshot

    def save(
        self,
        positions: Mapping[str, float],
        notionals: Mapping[str, float],
    ) -> None:
        self.saved.append((dict(positions), dict(notionals)))


def test_register_fill_tracks_signed_position_absolute_notional_and_persists() -> None:
    store = RecordingRiskStateStore()
    manager = RiskManager(RiskLimits(), risk_state_store=store)

    manager.register_fill("btc_usdt", "buy", qty=2.0, price=100.0)
    manager.register_fill("BTC/USDT", "sell", qty=0.5, price=120.0)

    assert manager.current_position("BTCUSDT") == pytest.approx(1.5)
    assert manager.current_notional("BTC/USDT") == pytest.approx(180.0)
    assert manager.exposure_snapshot() == {
        "BTC/USDT": {"position": 1.5, "notional": 180.0},
    }
    assert store.saved[-1] == (
        {"BTC/USDT": 1.5},
        {"BTC/USDT": 180.0},
    )


def test_exposure_snapshot_merges_notional_only_restored_state_sorted() -> None:
    store = RecordingRiskStateStore(
        positions={"eth_usdt": 3.0},
        notionals={"btc_usdt": 50_000.0, "eth_usdt": 6_000.0},
    )
    manager = RiskManager(RiskLimits(), risk_state_store=store)

    assert manager.exposure_snapshot() == {
        "BTC/USDT": {"position": 0.0, "notional": 50_000.0},
        "ETH/USDT": {"position": 3.0, "notional": 6_000.0},
    }


def test_portfolio_heat_is_gross_exposure_not_directional_netting() -> None:
    heat = portfolio_heat(
        [
            {"side": "long", "qty": 2.0, "price": 100.0, "risk_weight": 0.5},
            {"side": "short", "qty": 2.0, "price": 100.0, "risk_weight": 0.5},
        ]
    )

    assert heat == pytest.approx(200.0)
