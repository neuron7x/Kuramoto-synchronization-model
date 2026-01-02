# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Reliability tests for threat scenarios and policy-level checks.

Validates threat-model and policy gating behaviors:
- REL_THREAT_LIQUIDITY_SHOCK_001: Liquidity shock triggers blocked action
- REL_THREAT_VOLATILITY_SPIKE_001: Volatility spike triggers safe-mode
- REL_THREAT_DATA_SPOOF_001: Data spoofing (price jump) detected
- REL_POLICY_BLOCKED_ACTION_001: Policy deviation blocks action
- REL_POLICY_SAFE_MODE_001: Policy deviation triggers safe-mode transition
"""
from __future__ import annotations

import pandas as pd

from tacl.risk_gating import PreActionContext, RiskGatingConfig, RiskGatingEngine
from tradepulse.data_quality import ValidationConfig, validate_historical_data


def test_liquidity_shock_blocks_action() -> None:
    """Liquidity shock should block execution (REL_THREAT_LIQUIDITY_SHOCK_001)."""

    engine = RiskGatingEngine()
    context = PreActionContext(
        venue="test",
        symbol="BTCUSD",
        side="buy",
        quantity=1.0,
        liquidity=100_000.0,
    )

    decision = engine.check(context)

    assert decision.allowed is False
    assert decision.rollback is True
    assert "liquidity_dryup" in decision.reasons


def test_volatility_spike_triggers_safe_mode() -> None:
    """Volatility spikes should trigger safe mode (REL_THREAT_VOLATILITY_SPIKE_001)."""

    engine = RiskGatingEngine()
    context = PreActionContext(
        venue="test",
        symbol="ETHUSD",
        side="sell",
        quantity=2.0,
        volatility=0.08,
    )

    decision = engine.check(context)

    assert decision.allowed is True
    assert decision.safe_mode is True
    assert decision.policy_override == "conservative"
    assert "volatility_soft_breach" in decision.reasons


def test_data_spoofing_price_jump_detected() -> None:
    """Large price jumps should be flagged as spoofing (REL_THREAT_DATA_SPOOF_001)."""

    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    prices = pd.DataFrame(
        {
            "open": [100, 102, 500, 505],
            "high": [101, 103, 510, 510],
            "low": [99, 101, 490, 500],
            "close": [100, 102, 500, 505],
        },
        index=dates,
    )

    config = ValidationConfig(max_price_jump_pct=25.0)
    report = validate_historical_data(prices, config=config)
    jump_issues = [issue for issue in report.issues if issue.code == "LARGE_PRICE_JUMP"]

    assert report.warnings_count > 0
    assert len(jump_issues) > 0


def test_policy_deviation_blocks_action() -> None:
    """Hard policy deviation should block action (REL_POLICY_BLOCKED_ACTION_001)."""

    config = RiskGatingConfig(hard_policy_deviation=0.3)
    engine = RiskGatingEngine(config)
    context = PreActionContext(
        venue="test",
        symbol="SOLUSD",
        side="buy",
        quantity=1.5,
        policy_deviation=0.35,
    )

    decision = engine.check(context)

    assert decision.allowed is False
    assert decision.rollback is True
    assert "policy_deviation_hard" in decision.reasons


def test_policy_safe_mode_transition() -> None:
    """Soft policy deviation should trigger safe mode (REL_POLICY_SAFE_MODE_001)."""

    config = RiskGatingConfig(max_policy_deviation=0.15, safe_policy="defensive")
    engine = RiskGatingEngine(config)
    context = PreActionContext(
        venue="test",
        symbol="ADAUSD",
        side="sell",
        quantity=3.0,
        policy_deviation=0.2,
    )

    decision = engine.check(context)

    assert decision.allowed is True
    assert decision.safe_mode is True
    assert decision.policy_override == "defensive"
    assert "policy_deviation_soft" in decision.reasons
