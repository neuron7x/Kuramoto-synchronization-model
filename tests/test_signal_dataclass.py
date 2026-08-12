# mypy: disable-error-code="attr-defined,unused-ignore"
"""Tests for the canonical RegimeSignal dataclass."""

from __future__ import annotations

import time

from coherence_bridge.signal import Regime, RegimeSignal


def test_frozen_immutable() -> None:
    sig = RegimeSignal(
        timestamp_ns=time.time_ns(),
        instrument="EURUSD",
        gamma=1.0,
        order_parameter_R=0.5,
        ricci_curvature=0.0,
        lyapunov_max=0.0,
        regime=Regime.METASTABLE,
        regime_confidence=0.8,
        regime_duration_s=1.0,
        signal_strength=0.0,
        risk_scalar=1.0,
        sequence_number=0,
    )
    try:
        sig.gamma = 2.0  # type: ignore[misc]
        raise AssertionError("Frozen dataclass should reject mutation")
    except AttributeError:
        pass  # expected


def test_to_dict_roundtrip() -> None:
    sig = RegimeSignal(
        timestamp_ns=time.time_ns(),
        instrument="GBPUSD",
        gamma=0.8,
        order_parameter_R=0.6,
        ricci_curvature=-0.1,
        lyapunov_max=0.01,
        regime=Regime.COHERENT,
        regime_confidence=0.9,
        regime_duration_s=5.0,
        signal_strength=0.3,
        risk_scalar=0.8,
        sequence_number=42,
    )
    d = sig.to_dict()
    restored = RegimeSignal.from_dict(d)
    assert restored.instrument == sig.instrument
    assert restored.gamma == sig.gamma
    assert restored.regime == sig.regime
    assert restored.sequence_number == sig.sequence_number


def test_fail_closed_constructor() -> None:
    sig = RegimeSignal.fail_closed("EURUSD")
    assert sig.risk_scalar == 0.0
    assert sig.regime == Regime.UNKNOWN
    assert sig.instrument == "EURUSD"


def test_nan_gamma_auto_corrected() -> None:
    sig = RegimeSignal(
        timestamp_ns=time.time_ns(),
        instrument="X",
        gamma=float("nan"),
        order_parameter_R=0.5,
        ricci_curvature=0.0,
        lyapunov_max=0.0,
        regime=Regime.METASTABLE,
        regime_confidence=0.5,
        regime_duration_s=0.0,
        signal_strength=0.0,
        risk_scalar=0.5,
        sequence_number=0,
    )
    # __post_init__ should have corrected NaN gamma
    assert sig.gamma == 0.0
    assert sig.risk_scalar == 0.0
    assert sig.regime == Regime.UNKNOWN


def test_regime_enum_values() -> None:
    assert Regime.COHERENT.value == "COHERENT"
    assert Regime.METASTABLE.value == "METASTABLE"
    assert Regime.DECOHERENT.value == "DECOHERENT"
    assert Regime.CRITICAL.value == "CRITICAL"
    assert Regime.UNKNOWN.value == "UNKNOWN"
    assert len(Regime) == 5


def test_hashable() -> None:
    """Frozen dataclass → hashable → usable as dict key or in sets."""
    sig1 = RegimeSignal.fail_closed("A")
    sig2 = RegimeSignal.fail_closed("B")
    s = {sig1, sig2}
    assert len(s) == 2
