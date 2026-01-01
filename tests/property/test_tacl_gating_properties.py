# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import time

import pytest

try:  # pragma: no cover - optional dependency boundary
    from hypothesis import given, seed, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from runtime.energy_validator import EnergyConfig, EnergyValidator
from tacl.degradation import DegradationPolicy, apply_degradation
from tacl.risk_gating import PreActionContext, RiskGatingConfig, RiskGatingEngine

from .utils import property_seed, property_settings

_RISK_CFG = RiskGatingConfig()
_HARD_VOL_MIN = _RISK_CFG.hard_volatility
_SOFT_VOL_MIN = _RISK_CFG.max_volatility
_SOFT_VOL_MAX = max(_SOFT_VOL_MIN, _RISK_CFG.hard_volatility - 1e-6)


def _finite_floats(*, min_value: float, max_value: float) -> st.SearchStrategy[float]:
    return st.floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False,
    )


@seed(property_seed("test_risk_gate_hard_volatility_blocks"))
@settings(**property_settings("test_risk_gate_hard_volatility_blocks", max_examples=60))
@given(_finite_floats(min_value=_HARD_VOL_MIN, max_value=_HARD_VOL_MIN + 0.4))
def test_risk_gate_hard_volatility_blocks(volatility: float) -> None:
    cfg = RiskGatingConfig()
    gate = RiskGatingEngine(cfg)
    decision = gate.check(
        PreActionContext(
            venue="x",
            symbol="BTCUSDT",
            side="BUY",
            quantity=1.0,
            volatility=volatility,
        )
    )

    assert decision.allowed is False
    assert decision.rollback is True
    assert "volatility_hard_breach" in decision.reasons


@seed(property_seed("test_risk_gate_soft_volatility_enables_safe_mode"))
@settings(
    **property_settings("test_risk_gate_soft_volatility_enables_safe_mode", max_examples=60)
)
@given(_finite_floats(min_value=_SOFT_VOL_MIN, max_value=_SOFT_VOL_MAX))
def test_risk_gate_soft_volatility_enables_safe_mode(volatility: float) -> None:
    cfg = RiskGatingConfig()
    gate = RiskGatingEngine(cfg)
    decision = gate.check(
        PreActionContext(
            venue="x",
            symbol="BTCUSDT",
            side="BUY",
            quantity=1.0,
            volatility=volatility,
        )
    )

    assert decision.allowed is True
    assert decision.safe_mode is True
    assert decision.rollback is False
    assert decision.policy_override == cfg.safe_policy
    assert "volatility_soft_breach" in decision.reasons


@seed(property_seed("test_energy_penalty_monotonic"))
@settings(**property_settings("test_energy_penalty_monotonic", max_examples=80))
@given(
    _finite_floats(min_value=0.0, max_value=200.0),
    _finite_floats(min_value=0.0, max_value=200.0),
)
def test_energy_penalty_monotonic(value_a: float, value_b: float) -> None:
    config = EnergyConfig()
    validator = EnergyValidator(config)
    metric = config.get_metric("latency_p95")
    assert metric is not None
    total_weight = config.get_total_weight()

    low, high = sorted([value_a, value_b])

    penalty_low, headroom_low = validator.compute_penalty(
        metric.name, low, metric_config=metric, total_weight=total_weight
    )
    penalty_high, headroom_high = validator.compute_penalty(
        metric.name, high, metric_config=metric, total_weight=total_weight
    )

    assert penalty_low >= 0.0
    assert penalty_high >= 0.0
    assert penalty_low <= penalty_high + 1e-9
    assert headroom_low >= headroom_high - 1e-9


class _SlowGate:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def check(self, context: object):
        time.sleep(self.delay)
        return context


@seed(property_seed("test_degradation_timeout_fallback"))
@settings(**property_settings("test_degradation_timeout_fallback", max_examples=25))
@given(_finite_floats(min_value=0.002, max_value=0.01))
def test_degradation_timeout_fallback(timeout_s: float) -> None:
    policy = DegradationPolicy(timeout_s=timeout_s)
    decision, report = apply_degradation(
        _SlowGate(delay=timeout_s * 2.0),
        policy.fallback_decision,
        policy=policy,
    )

    assert report.degraded is True
    assert report.reason == "timeout"
    assert "timeout" in decision.reasons
    assert decision.allowed == policy.fallback_decision.allowed
