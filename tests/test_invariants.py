"""Tests for formal signal contract verification (13 theorems)."""

from __future__ import annotations

import time

import pytest

from coherence_bridge.invariants import (
    InvariantViolation,
    verify_signal,
    verify_T1,
    verify_T3,
    verify_T4,
    verify_T7,
    verify_T11,
    verify_T13,
)


def _valid_signal(**overrides) -> dict:
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
        "risk_scalar": 1.0,
        "sequence_number": 0,
    }
    base.update(overrides)
    return base


def test_all_theorems_pass_on_valid_signal() -> None:
    results = verify_signal(_valid_signal(), raise_on_failure=False)
    assert len(results) == 13
    for r in results:
        assert r.passed, f"{r.theorem} failed: {r.message}"


def test_T1_rejects_zero_timestamp() -> None:
    r = verify_T1(_valid_signal(timestamp_ns=0))
    assert not r.passed


def test_T3_rejects_negative_gamma() -> None:
    r = verify_T3(_valid_signal(gamma=-0.5))
    assert not r.passed


def test_T4_rejects_R_above_one() -> None:
    r = verify_T4(_valid_signal(order_parameter_R=1.01))
    assert not r.passed
    assert "INV-K1" in r.message


def test_T7_rejects_invalid_regime() -> None:
    r = verify_T7(_valid_signal(regime="INVALID"))
    assert not r.passed


def test_T11_checks_risk_gamma_consistency() -> None:
    # gamma=1.0 → risk_scalar should be 1.0
    r = verify_T11(_valid_signal(gamma=1.0, risk_scalar=1.0))
    assert r.passed

    # gamma=1.5 → risk_scalar should be 0.5, not 0.9
    r = verify_T11(_valid_signal(gamma=1.5, risk_scalar=0.9))
    assert not r.passed


def test_T13_fail_closed() -> None:
    # NaN gamma with risk=0 and regime=UNKNOWN → pass
    r = verify_T13(_valid_signal(gamma=float("nan"), risk_scalar=0.0, regime="UNKNOWN"))
    assert r.passed

    # NaN gamma with risk=0.5 → fail
    r = verify_T13(_valid_signal(gamma=float("nan"), risk_scalar=0.5, regime="UNKNOWN"))
    assert not r.passed


def test_verify_signal_raises_on_first_failure() -> None:
    with pytest.raises(InvariantViolation) as exc_info:
        verify_signal(_valid_signal(timestamp_ns=0), raise_on_failure=True)
    assert "T1" in str(exc_info.value)


def test_mock_engine_signals_pass_all_theorems() -> None:
    """Every MockEngine signal must pass all 13 invariant theorems."""
    from coherence_bridge.mock_engine import MockEngine

    engine = MockEngine()
    for _ in range(50):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            if sig is not None:
                results = verify_signal(sig, raise_on_failure=False)
                for r in results:
                    assert (
                        r.passed
                    ), f"MockEngine {inst} violates {r.theorem}: {r.message} signal={sig}"
