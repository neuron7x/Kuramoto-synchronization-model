# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""Tests for server signal sanitization (fail-closed behavior)."""

import time

from coherence_bridge.server import _sanitize_signal


def _make_signal(**overrides) -> dict:
    base = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.001,
        "regime": "METASTABLE",
        "regime_confidence": 0.8,
        "regime_duration_s": 10.0,
        "signal_strength": 0.1,
        "risk_scalar": 0.9,
        "sequence_number": 0,
    }
    base.update(overrides)
    return base


def test_sanitize_passes_valid_signal() -> None:
    sig = _make_signal(gamma=1.0)
    out = _sanitize_signal(sig)
    assert out["regime"] == "METASTABLE"
    assert out["risk_scalar"] == 0.9  # existing value preserved


def test_sanitize_nan_gamma_forces_unknown_zero_risk() -> None:
    sig = _make_signal(gamma=float("nan"))
    out = _sanitize_signal(sig)
    assert out["risk_scalar"] == 0.0
    assert out["regime"] == "UNKNOWN"


def test_sanitize_inf_gamma_forces_unknown_zero_risk() -> None:
    sig = _make_signal(gamma=float("inf"))
    out = _sanitize_signal(sig)
    assert out["risk_scalar"] == 0.0
    assert out["regime"] == "UNKNOWN"


def test_sanitize_negative_inf() -> None:
    sig = _make_signal(gamma=float("-inf"))
    out = _sanitize_signal(sig)
    assert out["risk_scalar"] == 0.0
    assert out["regime"] == "UNKNOWN"


def test_sanitize_fills_missing_risk_scalar() -> None:
    sig = _make_signal(gamma=1.2)
    del sig["risk_scalar"]
    out = _sanitize_signal(sig)
    assert abs(out["risk_scalar"] - 0.8) < 1e-10


def test_sanitize_does_not_mutate_original() -> None:
    sig = _make_signal(gamma=float("nan"))
    original_regime = sig["regime"]
    _sanitize_signal(sig)
    assert sig["regime"] == original_regime  # original untouched
