# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for the shared dataclasses / enums of ``modules``.

These are not import-smoke tests. Each assertion pins a behaviour a defect
could silently break: enum value sets, deterministic defaults, malformed-input
rejection, serialization round-trips, finiteness of artifact numeric fields,
timezone-stable timestamps, and deterministic equality/hash for frozen states.
"""

from __future__ import annotations

import math
from datetime import timezone

import pytest
from pydantic import ValidationError

from modules.adaptive_risk_manager import PositionLimit
from modules.agent_coordinator import (
    AgentCoordinator,
    AgentType,
    CoherenceAxes,
    SubjectiveState,
    utc_now,
)
from modules.gaba_inhibition_gate import GateParams
from modules.market_regime_analyzer import MarketRegimeAnalyzer, RegimeMetrics
from modules.order_validator import OrderSide, OrderType, RiskLimits, ValidationResult
from modules.signal_strategy_registry import StrategyStatus


# --------------------------------------------------------------------------- #
# Enum boundaries pinned — a renamed/added/removed member is a contract break.
# --------------------------------------------------------------------------- #
def test_order_enum_value_sets_are_pinned() -> None:
    assert {s.value for s in OrderSide} == {"buy", "sell"}
    assert {t.value for t in OrderType} == {"market", "limit", "stop", "stop_limit"}
    assert {v.value for v in ValidationResult} == {"passed", "failed", "warning"}


def test_unknown_enum_member_fails_closed() -> None:
    # An unknown status/side/verdict must raise, never coerce to a default.
    for enum_cls, bogus in (
        (OrderSide, "hold"),
        (ValidationResult, "maybe"),
        (StrategyStatus, "zombie"),
    ):
        with pytest.raises(ValueError):
            enum_cls(bogus)


# --------------------------------------------------------------------------- #
# Deterministic defaults.
# --------------------------------------------------------------------------- #
def test_risk_limits_defaults_are_deterministic() -> None:
    a = RiskLimits()
    b = RiskLimits()
    assert a == b
    # Pin the safety-critical defaults so a silent loosening is caught.
    assert a.max_leverage == 2.0
    assert a.max_concentration == 0.2
    assert a.min_order_size == 10.0


# --------------------------------------------------------------------------- #
# Malformed input rejected.
# --------------------------------------------------------------------------- #
def test_position_limit_rejects_out_of_range_fields() -> None:
    # Leverage above the pydantic cap must be rejected, not clamped.
    with pytest.raises(ValidationError):
        PositionLimit(symbol="X", max_position_size=1.0, max_leverage=11.0, stop_loss_pct=0.1)
    # stop_loss_pct must be a strict fraction in (0, 1).
    with pytest.raises(ValidationError):
        PositionLimit(symbol="X", max_position_size=1.0, max_leverage=2.0, stop_loss_pct=1.0)
    # Non-positive position size must be rejected (gt=0).
    with pytest.raises(ValidationError):
        PositionLimit(symbol="X", max_position_size=0.0, max_leverage=2.0, stop_loss_pct=0.1)


def test_gate_params_reject_unstable_configuration() -> None:
    with pytest.raises(ValueError):
        GateParams(dt_ms=-1.0)
    with pytest.raises(ValueError):
        GateParams(tau_gaba_a_ms=0.0)
    # max_inhibition must stay strictly inside (0, 1) — a bypass of the cap.
    with pytest.raises(ValueError):
        GateParams(max_inhibition=1.0)


# --------------------------------------------------------------------------- #
# Serialization round-trip.
# --------------------------------------------------------------------------- #
def test_gate_params_serialization_round_trip() -> None:
    original = GateParams(k_inhibit=0.37, gamma_hz=41.0)
    restored = GateParams.from_dict(original.as_dict())
    assert restored.as_dict() == original.as_dict()


def test_gate_params_from_dict_ignores_unknown_keys() -> None:
    payload = GateParams().as_dict()
    payload["not_a_real_field"] = 123
    restored = GateParams.from_dict(payload)
    assert not hasattr(restored, "not_a_real_field")
    assert restored.k_inhibit == GateParams().k_inhibit


# --------------------------------------------------------------------------- #
# No NaN/Inf in artifact numeric fields (regression: constant series leaked a
# NaN adf_statistic before the degenerate-design guard was added).
# --------------------------------------------------------------------------- #
def test_regime_metrics_numeric_fields_are_finite_on_constant_series() -> None:
    analyzer = MarketRegimeAnalyzer()
    metrics: RegimeMetrics = analyzer.classify_regime({"prices": [100.0] * 60})
    for name in (
        "volatility",
        "hurst_exponent",
        "adf_statistic",
        "adf_pvalue",
        "regime_confidence",
    ):
        value = getattr(metrics, name)
        assert math.isfinite(value), f"{name} is not finite: {value!r}"


# --------------------------------------------------------------------------- #
# Timezone-stable timestamps (agent coordinator UTC contract).
# --------------------------------------------------------------------------- #
def test_agent_timestamps_are_utc_aware() -> None:
    now = utc_now()
    assert now.tzinfo == timezone.utc
    coordinator = AgentCoordinator()
    meta = coordinator.register_agent(
        "a1", AgentType.TRADING, "n", "d", handler=object()
    )
    assert meta.registered_at.tzinfo == timezone.utc
    assert meta.last_active.tzinfo == timezone.utc


# --------------------------------------------------------------------------- #
# Deterministic equality / hash for frozen coherence states.
# --------------------------------------------------------------------------- #
def test_subjective_state_equality_and_hash_are_deterministic() -> None:
    axes = CoherenceAxes(1.0, 1.0, 1.0, 1.0, 1.0)
    a = SubjectiveState(axes=axes, coherence_score=1.0, entropy=0.0)
    b = SubjectiveState(axes=axes, coherence_score=1.0, entropy=0.0)
    assert a == b
    assert hash(a) == hash(b)
    assert a.state_class == "healthy"


def test_subjective_state_impossible_when_entropy_inconsistent() -> None:
    axes = CoherenceAxes(1.0, 1.0, 1.0, 1.0, 1.0)
    # entropy must equal 1 - coherence_score; an inconsistent pair is impossible.
    bad = SubjectiveState(axes=axes, coherence_score=1.0, entropy=0.9)
    assert bad.hidden_contradiction is True
    assert bad.state_class == "impossible"
    assert bad.truth is False
