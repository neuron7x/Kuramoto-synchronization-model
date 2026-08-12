# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: OMS notional risk gate must fail CLOSED on an unknown mark.

Bug: a market order carries no ``price`` pre-fill, and the OMS substituted a
nominal ``$1`` (``max(average_price or 0.0, 1.0)``) as the reference price for
the pre-trade notional check. ``qty * 1.0`` then slips under any real notional
cap, silently bypassing the limit for the most common order type.

Fix: when a finite notional cap is in force and no real reference price exists,
reject (fail closed). When no cap is configured the substitute is inert, so a
nominal positive value still admits ordinary market orders.

The ``execution.*`` packages are behind the ``forbidden_import_patterns``
architecture gate, so they are loaded via ``importlib.import_module`` (the
repo-sanctioned pattern; see ``grandfathered-forbidden-imports-fix``) rather
than a static ``from execution... import``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from domain import Order, OrderType

_oms = importlib.import_module("execution.oms")
_compliance = importlib.import_module("execution.compliance")
_connectors = importlib.import_module("execution.connectors")
_risk = importlib.import_module("execution.risk.core")

_risk_reference_price = _oms._risk_reference_price
OMSConfig = _oms.OMSConfig
OrderManagementSystem = _oms.OrderManagementSystem
ComplianceViolation = _compliance.ComplianceViolation
SimulatedExchangeConnector = _connectors.SimulatedExchangeConnector
RiskLimits = _risk.RiskLimits
RiskManager = _risk.RiskManager


def _market(price: float | None = None, average_price: float | None = None) -> Order:
    return Order(
        symbol="BTC/USDT",
        side="buy",
        quantity=1.0,
        price=price,
        order_type=OrderType.MARKET,
        average_price=average_price,
    )


# --------------------------------------------------------------------------- #
# Unit: the fail-open -> fail-closed reference-price logic
# --------------------------------------------------------------------------- #
def test_no_reference_price_with_cap_fails_closed() -> None:
    with pytest.raises(ComplianceViolation):
        _risk_reference_price(_market(), notional_cap_active=True)


def test_no_reference_price_without_cap_returns_nominal() -> None:
    # No notional gate to fool -> nominal positive price is inert, order admitted.
    assert _risk_reference_price(_market(), notional_cap_active=False) == 1.0


def test_explicit_price_is_used() -> None:
    assert _risk_reference_price(_market(price=50_000.0), notional_cap_active=True) == 50_000.0


def test_average_price_fallback_is_used() -> None:
    assert _risk_reference_price(_market(average_price=42.0), notional_cap_active=True) == 42.0


# --------------------------------------------------------------------------- #
# Integration: real RiskManager wiring through OMS.submit
# --------------------------------------------------------------------------- #
def _make_oms(tmp_path: Path, risk: Any) -> Any:
    config = OMSConfig(
        state_path=tmp_path / "oms-state.json",
        auto_persist=True,
        ledger_path=None,
        pre_trade_timeout=None,
    )
    return OrderManagementSystem(SimulatedExchangeConnector(), risk, config)


def test_market_order_rejected_when_notional_cap_active(tmp_path: Path) -> None:
    oms = _make_oms(tmp_path, RiskManager(RiskLimits(max_notional=10_000.0)))
    with pytest.raises(ComplianceViolation):
        oms.submit(_market(), correlation_id="corr-fail-closed")


def test_market_order_admitted_when_no_notional_cap(tmp_path: Path) -> None:
    # Default max_notional is +inf: no cap, so the substitute price is inert and
    # an ordinary market order is still admitted (no false rejection).
    oms = _make_oms(tmp_path, RiskManager(RiskLimits()))
    result = oms.submit(_market(), correlation_id="corr-admit")
    assert result is not None
